"""Verifie la structure des pages HTML du site.

Le 2026-08-11, une refonte de contenu a laisse dans parcours.html une balise
<article> ouverte deux fois et un </ul> orphelin. Aucun controle existant ne
l'a vu : les tests portaient sur le pipeline et sur la coherence de la FAQ,
verifier_liens sur les URL, verifier_jsonld sur le balisage schema.org.
Personne ne regardait si le HTML fermait ce qu'il ouvrait. Ce module comble
ce trou, sans dependance externe.

Trois controles :

1. Balises equilibrees, dans le bon ordre d'imbrication.
2. Aucune apostrophe courbe. Le site ecrit l'apostrophe droite partout ;
   un copier-coller depuis Word ou depuis un fichier de consignes en
   reintroduit sans qu'on le voie a la relecture.
3. Aucune esperluette nue. `&` doit etre `&amp;` hors entite HTML.

    python -m pipeline.verifier_html
"""

import re
import sys
from pathlib import Path

RACINE = Path(__file__).parent.parent

# Elements sans balise fermante en HTML5.
BALISES_ORPHELINES = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

# Contenu opaque : on n'y cherche pas de balises HTML.
MOTIF_OPAQUE = re.compile(r"<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>", re.DOTALL)
MOTIF_BALISE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(/?)>")
MOTIF_ENTITE = re.compile(r"&(#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")


def pages_du_site(racine=RACINE):
    """Toutes les pages HTML publiees, y compris celles des sous-dossiers."""
    ignores = {"node_modules", ".git"}
    return sorted(
        chemin
        for chemin in racine.rglob("*.html")
        if not any(partie in ignores for partie in chemin.parts)
    )


def _neutraliser(contenu):
    """Remplace commentaires, scripts et styles par des espaces, en gardant
    les sauts de ligne pour que les numeros de ligne restent justes."""
    return MOTIF_OPAQUE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), contenu)


def anomalies_de_balises(contenu):
    """Renvoie la liste des (ligne, message) de desequilibre de balises."""
    texte = _neutraliser(contenu)
    pile = []
    anomalies = []
    for correspondance in MOTIF_BALISE.finditer(texte):
        fermante, nom, _, autofermante = correspondance.groups()
        nom = nom.lower()
        if nom in BALISES_ORPHELINES or autofermante:
            continue
        ligne = texte.count("\n", 0, correspondance.start()) + 1
        if fermante:
            if pile and pile[-1][0] == nom:
                pile.pop()
            elif any(ouverte == nom for ouverte, _ in pile):
                attendue = pile[-1]
                anomalies.append((
                    ligne,
                    f"</{nom}> rencontre alors que <{attendue[0]}> "
                    f"(ligne {attendue[1]}) n'est pas fermee",
                ))
                while pile and pile[-1][0] != nom:
                    pile.pop()
                pile.pop()
            else:
                anomalies.append((ligne, f"</{nom}> ferme une balise jamais ouverte"))
        else:
            pile.append((nom, ligne))
    for nom, ligne in reversed(pile):
        anomalies.append((ligne, f"<{nom}> ouverte et jamais fermee"))
    return anomalies


def anomalies_de_typographie(contenu):
    """Apostrophes courbes et esperluettes nues."""
    anomalies = []
    texte = _neutraliser(contenu)
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        if "’" in ligne:
            anomalies.append((numero, "apostrophe courbe, le site utilise l'apostrophe droite"))
        for position in (m.start() for m in re.finditer(r"&", ligne)):
            if not MOTIF_ENTITE.match(ligne, position):
                anomalies.append((numero, "esperluette nue, ecrire &amp;"))
                break
    return anomalies


def verifier(chemin):
    """Renvoie la liste des (ligne, message) pour une page."""
    contenu = chemin.read_text(encoding="utf-8")
    return sorted(anomalies_de_balises(contenu) + anomalies_de_typographie(contenu))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    pages = [Path(a) for a in argv] if argv else pages_du_site()
    total = 0
    for page in pages:
        for ligne, message in verifier(page):
            total += 1
            print(f"{page}:{ligne} : {message}")
    if total:
        print(f"\n{total} anomalie(s) sur {len(pages)} page(s).")
        return 1
    print(f"Structure HTML valide : {len(pages)} page(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
