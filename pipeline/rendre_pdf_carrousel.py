"""Convertit un plan de carrousel valide en PDF carre pret pour LinkedIn.

Deuxieme moitie de la chaine ouverte par rendre_carrousel.py. Celui-la
propose un plan, Ulrich le relit et le corrige, celui-ci le met en page.
La separation est deliberee : le PDF ne doit jamais sortir d'une execution
automatique, sans quoi la relecture cesse d'etre une etape et devient une
formalite qu'on saute.

Le Markdown est lu comme une suite de diapositives : chaque titre de niveau
deux commencant par « Diapositive » ouvre un cadre, et tout ce qui suit
jusqu'au separateur en fait partie. Les sections « Texte du post »,
« Sources » et « A verifier » sont ignorees : elles servent a la relecture
et a la publication, pas au carrousel lui-meme.

Le format est 1080 x 1080 points CSS, celui que LinkedIn recadre le moins.
La mise en page reprend la palette du site et le lisere teal-vert-ambre qui
sert de signature a La Frontiere, pour qu'un carrousel partage renvoie
visuellement a djidonou.com.

Le rendu passe par Chrome en mode headless, deja installe sur le poste et
seul moteur disponible ici qui pagine correctement une taille personnalisee.

    python -m pipeline.rendre_pdf_carrousel carrousels/2026-08-29-frontiere.md
    python -m pipeline.rendre_pdf_carrousel <plan.md> --sortie <fichier.pdf>
"""

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

COTE = 1080

# Sections du plan qui ne sont pas des diapositives : elles accompagnent la
# relecture et la publication du post, et n'ont rien a faire dans le PDF.
HORS_CARROUSEL = ("Texte du post", "Sources", "A verifier", "À vérifier")

CHROMES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

GABARIT = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><style>
  @page {{ size: {cote}px {cote}px; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: #fffdf8; }}
  .slide {{
    width: {cote}px; height: {cote}px;
    page-break-after: always; break-after: page;
    position: relative; overflow: hidden;
    background: #fffdf8; color: #16201f;
    padding: 86px; display: flex; flex-direction: column; gap: 30px;
    font-family: Georgia, "Times New Roman", serif;
  }}
  .slide:last-child {{ page-break-after: auto; break-after: auto; }}
  .slide::before {{
    content: ""; position: absolute; top: 0; left: 0; right: 0; height: 17px;
    background: linear-gradient(90deg, #0b5c5a 0%, #7b9e53 55%, #c38a2e 100%);
  }}
  .eyebrow {{
    font-family: "Trebuchet MS", Verdana, sans-serif;
    font-size: 29px; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; color: #073f3d;
  }}
  h3 {{ font-size: calc(var(--k) * 69px); font-weight: 700; line-height: 1.14; margin: 0; }}
  h3.grand {{ font-size: calc(var(--k) * 88px); }}
  p {{ font-size: calc(var(--k) * 43px); line-height: 1.42; margin: 0; }}
  p.petit {{ font-size: calc(var(--k) * 38px); }}
  .ref {{
    font-family: "Trebuchet MS", Verdana, sans-serif;
    font-size: calc(var(--k) * 32px); line-height: 1.4; color: #56635f;
  }}
  .spacer {{ flex: 1; }}
  .pied {{
    font-family: "Trebuchet MS", Verdana, sans-serif;
    font-size: 29px; color: #56635f;
    display: flex; justify-content: space-between; gap: 24px;
    border-top: 1px solid #e2dccf; padding-top: 32px;
  }}
  .signature {{
    font-weight: 700; color: #073f3d;
    letter-spacing: 0.06em; text-transform: uppercase;
  }}
</style></head><body>
{corps}
</body></html>
"""


def trouver_chrome():
    for chemin in CHROMES:
        if Path(chemin).exists():
            return chemin
    trouve = shutil.which("chrome") or shutil.which("chrome.exe")
    if trouve:
        return trouve
    raise SystemExit(
        "Chrome introuvable. Installe-le, ou passe son chemin par la variable "
        "CHROME. Aucun autre moteur du poste ne pagine une taille carree."
    )


def decouper(markdown):
    """Rend la liste des diapositives : (role, [paragraphes])."""
    diapositives = []
    courante = None
    for ligne in markdown.splitlines():
        titre = re.match(r"^##\s+Diapositives?\s+\d+\s*,\s*(.+?)\s*$", ligne)
        if titre:
            courante = {"role": titre.group(1), "lignes": []}
            diapositives.append(courante)
            continue
        if re.match(r"^#\s+", ligne) or re.match(r"^##\s+", ligne):
            # Une section hors carrousel ferme la diapositive en cours.
            courante = None
            continue
        if ligne.strip() == "---":
            courante = None
            continue
        if courante is not None:
            courante["lignes"].append(ligne)
    return [d for d in diapositives if any(l.strip() for l in d["lignes"])]


def paragraphes(lignes):
    """Regroupe les lignes en paragraphes, en gardant les retours simples."""
    blocs, courant = [], []
    for ligne in lignes:
        if ligne.strip():
            courant.append(ligne.strip())
        elif courant:
            blocs.append(courant)
            courant = []
    if courant:
        blocs.append(courant)
    return blocs


def enrichir(texte):
    """Gras, italique et liens Markdown vers du HTML, le reste echappe."""
    sortie = html.escape(texte)
    sortie = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", sortie)
    sortie = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", sortie)
    return sortie


def echelle(lignes):
    """Facteur de taille du texte, pour qu'une diapositive dense tienne.

    Un cadre carre ne s'allonge pas : au-dela d'un certain volume, le texte
    depasse et Chrome le coupe en silence. Le debordement ne se voit alors
    que sur le PDF final, une fois le carrousel deja publie.
    """
    volume = sum(len(ligne) for ligne in lignes)
    for seuil, facteur in ((360, 1.0), (460, 0.92), (560, 0.84), (680, 0.76)):
        if volume <= seuil:
            return facteur
    return 0.68


def rendre_diapositive(index, total, diapositive):
    blocs = paragraphes(diapositive["lignes"])
    facteur = echelle(diapositive["lignes"])
    morceaux = [f'<section class="slide" style="--k: {facteur}">']
    # « Couverture » et « question de cloture » nomment le role de la
    # diapositive dans le plan, pas son contenu : les afficher ferait passer
    # une etiquette de production dans l'image publiee.
    if index == 1:
        chapeau = "La Frontière"
    elif index == total:
        chapeau = "À vous"
    else:
        chapeau = diapositive["role"]
    morceaux.append(f'<div class="eyebrow">{html.escape(chapeau)}</div>')

    pied_droit = "djidonou.com/frontiere"
    corps = []
    for bloc in blocs:
        texte = "<br>".join(enrichir(l) for l in bloc)
        brut = " ".join(bloc)
        if brut.startswith("Source :"):
            # La source alimente le pied de page plutot qu'un paragraphe.
            pied_droit = html.escape(brut.replace("Source :", "").strip())
            pied_droit = pied_droit.replace("https://", "").replace("http://", "")
            continue
        if bloc[0].startswith("**") and bloc[0].endswith("**") and len(blocs) <= 3:
            classe = "grand" if index == 1 else ""
            corps.append(f'<h3 class="{classe}">{enrichir(bloc[0].strip("*"))}</h3>')
            continue
        if len(bloc) > 1 and "," in bloc[-1] and len(brut) < 160 and bloc[0].startswith("**"):
            corps.append(f'<h3>{enrichir(bloc[0].strip("*"))}</h3>')
            corps.append(f'<p class="ref">{"<br>".join(enrichir(l) for l in bloc[1:])}</p>')
            continue
        classe = "petit" if len(brut) > 190 else ""
        corps.append(f'<p class="{classe}">{texte}</p>')

    if index == 1 or index == total:
        morceaux.append('<div class="spacer"></div>')
        morceaux += corps
        morceaux.append('<div class="spacer"></div>')
        gauche = "Ulrich Djidonou"
    else:
        morceaux += corps
        morceaux.append('<div class="spacer"></div>')
        gauche = f"{index:02d}"

    morceaux.append(
        f'<div class="pied"><span class="signature">{gauche}</span>'
        f"<span>{pied_droit}</span></div>"
    )
    morceaux.append("</section>")
    return "\n".join(morceaux)


def rendre_html(diapositives):
    total = len(diapositives)
    corps = "\n".join(
        rendre_diapositive(i, total, d) for i, d in enumerate(diapositives, start=1)
    )
    return GABARIT.format(cote=COTE, corps=corps)


def rendre_pdf(chemin_html, sortie, chrome):
    with tempfile.TemporaryDirectory() as profil:
        subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                f"--user-data-dir={profil}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={sortie}",
                Path(chemin_html).resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )


def main(argv=None):
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("plan", help="plan Markdown valide")
    analyseur.add_argument("--sortie", help="fichier PDF a ecrire")
    arguments = analyseur.parse_args(argv)

    plan = Path(arguments.plan)
    if not plan.exists():
        raise SystemExit(f"{plan} introuvable.")

    markdown = plan.read_text(encoding="utf-8")
    if "[A COMPLETER]" in markdown:
        raise SystemExit(
            f"{plan} contient encore des emplacements [A COMPLETER]. Le PDF "
            "sortirait avec des trous a la place de ton angle : complete le "
            "plan d'abord."
        )

    diapositives = decouper(markdown)
    if not diapositives:
        raise SystemExit(f"Aucune diapositive reconnue dans {plan}.")

    sortie = Path(arguments.sortie) if arguments.sortie else plan.with_suffix(".pdf")
    chrome = os.environ.get("CHROME") or trouver_chrome()

    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as fichier:
        fichier.write(rendre_html(diapositives))
        temporaire = fichier.name
    try:
        rendre_pdf(temporaire, sortie.resolve(), chrome)
    finally:
        Path(temporaire).unlink(missing_ok=True)

    print(f"{len(diapositives)} diapositives ecrites dans {sortie}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
