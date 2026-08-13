"""Verifie la presence et la rigueur de la Content-Security-Policy (CSP).

Les 8 pages publiques (plus 404.html) portent une balise
<meta http-equiv="Content-Security-Policy">. Cette protection ne vaut que
tant qu'elle est presente partout. Une page creee plus tard par copie d'un
ancien gabarit l'oublierait sans que rien ne le signale. C'est un risque
concret : faq.html a justement ete creee par copie de ressources.html.

Controles effectues sur chaque page HTML publiee du site :
1. Presence de la balise <meta http-equiv="Content-Security-Policy">.
2. Absence des directives 'unsafe-inline' et 'unsafe-eval' dans la CSP.

    python -m pipeline.verifier_csp
"""

import re
import sys
from pathlib import Path
from pipeline.verifier_html import RACINE, pages_du_site

# Outils internes et jetons de verification qui ne sont pas des pages HTML du site.
EXCLUSIONS = {
    "pipeline/benchmark/evaluation_aveugle.html",
}

MOTIF_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE | re.DOTALL)
MOTIF_HTTP_EQUIV = re.compile(
    r'\bhttp-equiv=["\']?content-security-policy["\']?', re.IGNORECASE
)
MOTIF_CONTENT = re.compile(
    r'\bcontent=(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE | re.DOTALL
)


def est_page_exclue(chemin, racine=RACINE):
    """Determine si un fichier HTML doit etre exclu du controle CSP.

    Exclut explicitement :
    - pipeline/benchmark/evaluation_aveugle.html : outil interne d'evaluation avec script inline.
    - google*.html : jetons de verification Google Search Console (ex. googlecf114224fc2202e7.html).
    """
    nom_fichier = chemin.name
    if nom_fichier.startswith("google") and nom_fichier.endswith(".html"):
        return True

    try:
        relatif = chemin.resolve().relative_to(racine.resolve()).as_posix()
    except ValueError:
        relatif = chemin.as_posix()

    return relatif in EXCLUSIONS


def anomalies_csp(contenu):
    """Renvoie la liste des (ligne, message) d'anomalies de CSP dans le contenu HTML."""
    anomalies = []
    balise_trouvee = False

    for match_meta in MOTIF_META.finditer(contenu):
        texte_meta = match_meta.group(0)
        if not MOTIF_HTTP_EQUIV.search(texte_meta):
            continue

        balise_trouvee = True
        ligne = contenu.count("\n", 0, match_meta.start()) + 1
        match_content = MOTIF_CONTENT.search(texte_meta)

        if not match_content:
            anomalies.append((ligne, "balise meta Content-Security-Policy sans attribut content"))
            continue

        valeur_raw = match_content.group(1) if match_content.group(1) is not None else match_content.group(2)
        valeur_csp = valeur_raw.lower()

        if "unsafe-inline" in valeur_csp:
            anomalies.append((ligne, "Content-Security-Policy autorise 'unsafe-inline'"))

        if "unsafe-eval" in valeur_csp:
            anomalies.append((ligne, "Content-Security-Policy autorise 'unsafe-eval'"))

    if not balise_trouvee:
        anomalies.append((1, "balise meta Content-Security-Policy absente"))

    return anomalies


def verifier(chemin):
    """Renvoie la liste des (ligne, message) pour une page."""
    contenu = chemin.read_text(encoding="utf-8")
    return sorted(anomalies_csp(contenu))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        pages = [Path(a) for a in argv if not est_page_exclue(Path(a))]
    else:
        pages = [p for p in pages_du_site() if not est_page_exclue(p)]

    total = 0
    for page in pages:
        for ligne, message in verifier(page):
            total += 1
            print(f"{page}:{ligne} : {message}")

    if total:
        print(f"\n{total} anomalie(s) sur {len(pages)} page(s).")
        return 1

    print(f"Content-Security-Policy valide : {len(pages)} page(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
