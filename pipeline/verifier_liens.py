"""Verifie que les liens sortants des pages publiees repondent encore.

Un projet peut disparaitre, changer d'hebergeur ou passer derriere une
authentification sans que rien ne le signale : la page continue d'afficher
un lien qui mene desormais a une erreur ou a un ecran de connexion. Le cas
s'est produit avec un tableau de bord Streamlit devenu prive, reste affiche
comme preuve publique. Ce controle transforme cette decouverte fortuite en
verification hebdomadaire.

Ne verifie que les liens absolus (http/https) : les liens internes sont
couverts par la construction du site elle-meme.

Une redirection vers une page de connexion est traitee comme un echec, meme
si elle repond 200 : pour un visiteur, un lien qui exige un compte n'est pas
un lien public.

    python -m pipeline.verifier_liens
    python -m pipeline.verifier_liens --rapport-seul   # n'echoue jamais
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent

TIMEOUT = 30
NAVIGATEUR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    )
}

MOTIF_LIEN = re.compile(r'href="(https?://[^"]+)"')

# Hotes ignores : ils repondent normalement dans un navigateur mais servent un
# 403 ou un captcha aux clients automatises, ce qui produirait une fausse
# alerte chaque semaine.
HOTES_IGNORES = (
    "linkedin.com",
    "www.linkedin.com",
    "x.com",
    "twitter.com",
)

# Une URL contenant un de ces fragments signale que le lien mene a une
# authentification plutot qu'au contenu annonce. La chaine de redirection
# entiere est inspectee, pas seulement l'URL finale : Streamlit renvoie
# l'ecran de connexion a l'adresse d'origine, donc le lien repond 200 sur son
# URL de depart alors qu'il a traverse /-/auth/ puis /-/login en chemin.
INDICES_AUTHENTIFICATION = ("/login", "/auth/", "signin", "sign-in", "oauth")


def pages_a_verifier():
    """Toutes les pages HTML publiees, hors artefacts de travail."""
    pages = sorted(RACINE.glob("*.html"))
    pages += sorted((RACINE / "frontiere").glob("*.html"))
    return pages


def extraire_liens(chemin):
    contenu = chemin.read_text(encoding="utf-8")
    return sorted(set(MOTIF_LIEN.findall(contenu)))


def hote_ignore(url):
    return urlparse(url).netloc.lower() in HOTES_IGNORES


def verifier(url):
    """Retourne None si le lien est sain, sinon la raison de l'echec."""
    try:
        # Certains hebergeurs refusent HEAD : on demande directement le GET,
        # en flux pour ne pas telecharger la page entiere.
        reponse = requests.get(
            url, timeout=TIMEOUT, headers=NAVIGATEUR, allow_redirects=True, stream=True
        )
        reponse.close()
    except requests.RequestException as erreur:
        return f"injoignable ({type(erreur).__name__})"

    if reponse.status_code >= 400:
        return f"HTTP {reponse.status_code}"

    parcourues = [etape.url for etape in reponse.history] + [reponse.url]
    for etape in parcourues:
        if any(indice in etape.lower() for indice in INDICES_AUTHENTIFICATION):
            return f"passe par une authentification ({etape.split('?')[0]})"

    return None


def main():
    rapport_seul = "--rapport-seul" in sys.argv

    echecs = []
    deja_vus = {}

    for page in pages_a_verifier():
        for url in extraire_liens(page):
            if hote_ignore(url):
                continue
            if url not in deja_vus:
                deja_vus[url] = verifier(url)
            probleme = deja_vus[url]
            if probleme:
                echecs.append((page.relative_to(RACINE).as_posix(), url, probleme))

    print(f"{len(deja_vus)} liens absolus verifies sur "
          f"{len(pages_a_verifier())} pages.")

    if not echecs:
        print("Aucun lien mort.")
        return 0

    print(f"\n{len(echecs)} lien(s) a corriger :")
    for page, url, probleme in echecs:
        print(f"  {page} : {url}\n      {probleme}")

    return 0 if rapport_seul else 1


if __name__ == "__main__":
    raise SystemExit(main())
