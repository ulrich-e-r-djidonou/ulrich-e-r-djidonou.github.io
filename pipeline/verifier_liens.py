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

Un lien qu'on n'a pas pu joindre n'est pas un lien mort. Quand un hebergeur
limite le debit sans desemparer, le controle le rapporte comme indetermine
et n'echoue pas : il n'y a rien a corriger dans la page. Voir Probleme.

    python -m pipeline.verifier_liens
    python -m pipeline.verifier_liens --rapport-seul   # n'echoue jamais
"""

import re
import sys
import time
from collections import namedtuple
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

# Codes qui traduisent une limitation de debit ou une indisponibilite passagere
# plutot qu'un lien mort. archive.org a renvoye un 498 le 13 aout 2026 sur une
# URL qui repondait 200 quelques minutes plus tard : sans reprise, ce controle
# hebdomadaire echoue au hasard des humeurs des hebergeurs.
CODES_TRANSITOIRES = frozenset({408, 425, 429, 498, 500, 502, 503, 504})
TENTATIVES = 3
ATTENTE_ENTRE_TENTATIVES = 5

# bloquant=False : le lien n'a pas pu etre joint, mais rien n'indique qu'il
# soit mort. Distinguer les deux est tout l'interet de ce module depuis le
# 13 aout 2026 : archive.org repond 503 aux adresses IP des runners GitHub
# tout en repondant 200 depuis un poste ordinaire, verifie trois fois de
# suite. Faire echouer la CI la-dessus demanderait de « corriger » un lien
# parfaitement valide, et apprendrait surtout a ignorer le rouge.
Probleme = namedtuple("Probleme", ("raison", "bloquant"))

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

# Le site lui-meme. Ses liens ne se verifient pas par le reseau : ce workflow
# se declenche au push sur main, avant que GitHub Pages ait fini de deployer.
# Une page neuve n'est donc pas encore en ligne quand le controle la demande,
# et repond 404. Constate le 13 aout 2026 sur faq.html, creee par la PR #12 :
# echec du controle alors que la page etait parfaitement valide, et le serait
# a chaque ajout de page a l'avenir. Une alerte qui se declenche a tort de
# facon previsible apprend surtout a ignorer le rouge.
#
# Interroger le reseau pour son propre site est de toute facon la mauvaise
# question : cela verifie le deploiement precedent, pas celui qu'on s'apprete
# a publier. Le disque, lui, porte l'etat exact qui partira en ligne.
HOTE_DU_SITE = "djidonou.com"

# Les fichiers qu'un repertoire sert quand l'URL s'arrete sur un slash.
INDEX_IMPLICITES = ("index.html",)


def chemin_local(url):
    """Chemin dans le depot correspondant a une URL du site, ou None.

    None signale que ce depot ne possede pas cette adresse : les projets
    (geoecon-pulse, AI-CA, ia-quebec-dashboard...) vivent dans leurs propres
    depots et sont servis sous le meme domaine. Eux se verifient bien par le
    reseau, seul endroit ou leur existence est observable d'ici.
    """
    partie = urlparse(url)
    if partie.netloc.lower().removeprefix("www.") != HOTE_DU_SITE:
        return None

    relatif = partie.path.lstrip("/")
    candidats = [relatif] if relatif else []
    if not relatif or relatif.endswith("/"):
        candidats += [relatif + index for index in INDEX_IMPLICITES]

    for candidat in candidats:
        chemin = (RACINE / candidat).resolve()
        # Garde-fou contre un « ../ » dans une URL : on ne sort pas du depot.
        if not chemin.is_relative_to(RACINE.resolve()):
            return None
        if chemin.is_file():
            return chemin

    return None


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


def verifier_par_le_reseau(url):
    """Retourne None si le lien repond, sinon un Probleme."""
    reponse = None
    for tentative in range(TENTATIVES):
        try:
            # Certains hebergeurs refusent HEAD : on demande directement le
            # GET, en flux pour ne pas telecharger la page entiere.
            reponse = requests.get(
                url, timeout=TIMEOUT, headers=NAVIGATEUR, allow_redirects=True, stream=True
            )
            reponse.close()
        except requests.RequestException as erreur:
            if tentative + 1 == TENTATIVES:
                # Injoignable apres plusieurs essais : reseau coupe, DNS,
                # timeout. Rien ne dit que la page est morte.
                return Probleme(f"injoignable ({type(erreur).__name__})", bloquant=False)
            time.sleep(ATTENTE_ENTRE_TENTATIVES)
            continue

        if reponse.status_code not in CODES_TRANSITOIRES:
            break
        if tentative + 1 < TENTATIVES:
            time.sleep(ATTENTE_ENTRE_TENTATIVES)

    if reponse.status_code in CODES_TRANSITOIRES:
        return Probleme(
            f"HTTP {reponse.status_code} apres {TENTATIVES} essais "
            f"(limitation de debit ou panne passagere, pas un lien mort)",
            bloquant=False,
        )

    if reponse.status_code >= 400:
        return Probleme(f"HTTP {reponse.status_code}", bloquant=True)

    parcourues = [etape.url for etape in reponse.history] + [reponse.url]
    for etape in parcourues:
        if any(indice in etape.lower() for indice in INDICES_AUTHENTIFICATION):
            return Probleme(
                f"passe par une authentification ({etape.split('?')[0]})", bloquant=True
            )

    return None


def verifier(url):
    """Retourne None si le lien est sain, sinon un Probleme.

    Une adresse que ce depot possede est tranchee sur le disque ; tout le
    reste par le reseau, y compris les adresses du site absentes du depot
    (projets heberges ailleurs, ou page reellement supprimee : seul le
    reseau distingue les deux). Voir chemin_local() pour le pourquoi.
    """
    if chemin_local(url) is not None:
        return None

    return verifier_par_le_reseau(url)


def main():
    rapport_seul = "--rapport-seul" in sys.argv

    a_corriger = []
    indetermines = []
    deja_vus = {}

    for page in pages_a_verifier():
        for url in extraire_liens(page):
            if hote_ignore(url):
                continue
            if url not in deja_vus:
                deja_vus[url] = verifier(url)
            probleme = deja_vus[url]
            if probleme is None:
                continue
            entree = (page.relative_to(RACINE).as_posix(), url, probleme.raison)
            (a_corriger if probleme.bloquant else indetermines).append(entree)

    print(f"{len(deja_vus)} liens absolus verifies sur "
          f"{len(pages_a_verifier())} pages.")

    # Rapporte avant le verdict : un lien qu'on n'a pas pu joindre reste une
    # information utile, meme s'il ne fait echouer personne.
    if indetermines:
        print(f"\n{len(indetermines)} lien(s) non verifiable(s) pour l'instant :")
        for page, url, raison in indetermines:
            print(f"  {page} : {url}\n      {raison}")

    if not a_corriger:
        print("\nAucun lien mort.")
        return 0

    print(f"\n{len(a_corriger)} lien(s) a corriger :")
    for page, url, raison in a_corriger:
        print(f"  {page} : {url}\n      {raison}")

    return 0 if rapport_seul else 1


if __name__ == "__main__":
    raise SystemExit(main())
