"""Aligne le lastmod des pages fixes de sitemap.xml sur leur dernier commit editorial.

Les deux pages de La Frontiere sont exclues : publish.synchroniser_sitemap()
les tient a jour a chaque publication du flux.

Un commit est editorial s'il ne vient pas d'un robot. Le robot etat-projets
touche chaque jour projets.html, en/projects.html et l'accueil pour les
etiquettes de fraicheur : compter ces commits ferait annoncer aux moteurs une
page modifiee chaque jour alors que son contenu n'a pas change.

Usage :
    python -m pipeline.maj_sitemap             # reecrit sitemap.xml
    python -m pipeline.maj_sitemap --verifier  # n'ecrit rien ; code 1 si une date est en retard

Le mode --verifier exige l'historique complet (actions/checkout avec
fetch-depth: 0) : sur un clone superficiel, git log ne voit qu'un commit.
"""

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

RACINE = Path(__file__).parent.parent
SITEMAP = RACINE / "sitemap.xml"

# URL publiee -> fichier source, d'apres le tableau de double langue de
# CONTRIBUTING.md. La Frontiere n'y figure pas (voir le docstring).
PAGES = {
    "https://djidonou.com/": "index.html",
    "https://djidonou.com/en/": "en/index.html",
    "https://djidonou.com/projets.html": "projets.html",
    "https://djidonou.com/en/projects.html": "en/projects.html",
    "https://djidonou.com/parcours.html": "parcours.html",
    "https://djidonou.com/en/career.html": "en/career.html",
    "https://djidonou.com/ressources.html": "ressources.html",
    "https://djidonou.com/en/resources.html": "en/resources.html",
    "https://djidonou.com/faq.html": "faq.html",
    "https://djidonou.com/en/faq.html": "en/faq.html",
    "https://djidonou.com/contact.html": "contact.html",
    "https://djidonou.com/en/contact.html": "en/contact.html",
}

# Messages des commits de robots, ecartes du calcul.
MOTIFS_ROBOTS = ("etiquettes de fraicheur", "mise a jour automatique")


def date_editoriale(fichier, racine=RACINE):
    """Date (AAAA-MM-JJ) du dernier commit non automatique qui touche le fichier."""
    commande = ["git", "-C", str(racine), "log", "-1", "--format=%cs", "--invert-grep"]
    for motif in MOTIFS_ROBOTS:
        commande += ["--grep", motif]
    commande += ["--", fichier]
    sortie = subprocess.run(
        commande, capture_output=True, text=True, encoding="utf-8", check=True
    ).stdout.strip()
    if not sortie:
        raise ValueError(f"aucun commit editorial trouve pour {fichier}")
    return sortie


def motif_entree(url):
    # Les xhtml:link s'intercalent entre <loc> et <lastmod>, comme dans
    # publish.synchroniser_sitemap().
    return re.compile(
        r"(<url>\s*<loc>" + re.escape(url) + r"</loc>"
        r"(?:\s*<xhtml:link[^>]*/>)*\s*<lastmod>)([^<]+)(</lastmod>)"
    )


def dates_attendues(racine=RACINE):
    return {url: date_editoriale(fichier, racine) for url, fichier in PAGES.items()}


def appliquer(contenu, attendues):
    """Renvoie (nouveau contenu, liste des (url, ancienne, nouvelle) modifiees)."""
    changements = []
    for url, nouvelle in attendues.items():
        motif = motif_entree(url)
        correspondance = motif.search(contenu)
        if correspondance is None:
            raise ValueError(f"entree {url} introuvable ou invalide dans sitemap.xml")
        ancienne = correspondance.group(2)
        if ancienne != nouvelle:
            changements.append((url, ancienne, nouvelle))
        contenu = motif.sub(
            lambda m: f"{m.group(1)}{nouvelle}{m.group(3)}", contenu, count=1
        )
    return contenu, changements


def en_retard(contenu, attendues):
    """Entrees dont le lastmod est anterieur au dernier commit editorial."""
    retards = []
    for url, attendue in attendues.items():
        correspondance = motif_entree(url).search(contenu)
        if correspondance is None:
            raise ValueError(f"entree {url} introuvable ou invalide dans sitemap.xml")
        publiee = correspondance.group(2)
        if date.fromisoformat(publiee) < date.fromisoformat(attendue):
            retards.append((url, publiee, attendue))
    return retards


def main(argv=None, racine=RACINE):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--verifier", action="store_true",
                         help="n'ecrit rien ; code 1 si un lastmod est en retard")
    args = parseur.parse_args(argv)

    sitemap = racine / "sitemap.xml"
    contenu = sitemap.read_text(encoding="utf-8")
    attendues = dates_attendues(racine)

    if args.verifier:
        retards = en_retard(contenu, attendues)
        for url, publiee, attendue in retards:
            print(f"{url} : lastmod {publiee}, dernier commit editorial {attendue}")
        if retards:
            print("Lancer : python -m pipeline.maj_sitemap")
            return 1
        print(f"sitemap.xml a jour ({len(attendues)} pages fixes verifiees)")
        return 0

    nouveau, changements = appliquer(contenu, attendues)
    if nouveau != contenu:
        sitemap.write_text(nouveau, encoding="utf-8", newline="\n")
    for url, ancienne, nouvelle in changements:
        print(f"{url} : {ancienne} -> {nouvelle}")
    print(f"{len(changements)} lastmod modifie(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
