"""Retelecharge l'abstract des items publies qui n'en ont plus localement.

Le rattrapage anglais (regenerer_flux --anglais) redige depuis l'abstract
d'origine. Les items collectes avant la mise en place du corpus fige n'ont
plus le leur : ils gardent leur seul francais et la page /en/ sert ce
francais en repli, ce qui est exactement ce qu'on cherche a supprimer.

Ce module va rechercher ces abstracts a la source et les ecrit dans
_abstracts_rattrapage.json, lu par regenerer_flux.charger_abstracts comme
troisieme source. L'ecart assume : un abstract retelecharge n'est pas
forcement mot pour mot celui qui a servi a rediger le francais publie. Le
risque est faible sur des documents de recherche, qui ne sont pas reecrits
apres publication, et il vaut mieux que servir du francais sur la page
anglaise.

    python -m pipeline.collecter_abstracts_manquants
"""

import html
import json
import re
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

import requests

RACINE = Path(__file__).parent.parent
FLUX = RACINE / "frontiere" / "data" / "flux.json"
SORTIE = Path(__file__).parent / "_abstracts_rattrapage.json"
ENTETES = {"User-Agent": "LaFrontiere/1.0 (https://djidonou.com)"}
TIMEOUT = 45
ARXIV_API = "https://export.arxiv.org/api/query"
NBER_RSS = "https://www.nber.org/rss/new.xml"
CEPR_RSS = "https://cepr.org/rss/vox-content"
OPENALEX = "https://api.openalex.org/works/https://doi.org/"
COURRIEL_OPENALEX = "romariche@gmail.com"

_cache_nber_rss = {}
_cache_cepr_rss = {}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def nettoyer(texte):
    sans_balises = re.sub(r"<[^>]+>", " ", texte or "")
    return " ".join(html.unescape(sans_balises).split())


def abstract_arxiv(url):
    identifiant = url.rsplit("/", 1)[-1]
    reponse = requests.get(
        ARXIV_API,
        params={"id_list": identifiant, "max_results": 1},
        headers=ENTETES,
        timeout=TIMEOUT,
    )
    reponse.raise_for_status()
    racine = ElementTree.fromstring(reponse.text)
    espace = "{http://www.w3.org/2005/Atom}"
    for entree in racine.iter(f"{espace}entry"):
        resume = entree.findtext(f"{espace}summary")
        if resume:
            return nettoyer(resume)
    return ""


def abstract_meta(url):
    """Balise citation_abstract, og:description ou description de la page."""
    reponse = requests.get(url, headers=ENTETES, timeout=TIMEOUT)
    reponse.raise_for_status()
    page = reponse.text
    for motif in (
        r'<meta[^>]+name=["\']citation_abstract["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
    ):
        trouve = re.search(motif, page, re.S | re.I)
        if trouve:
            texte = nettoyer(trouve.group(1))
            if len(texte) > 200:
                return texte
    return ""


def abstract_openalex(doi):
    """OpenAlex rend l'abstract sous forme d'index inverse, a reconstituer."""
    reponse = requests.get(
        OPENALEX + doi,
        headers={**ENTETES, "mailto": COURRIEL_OPENALEX},
        timeout=TIMEOUT,
    )
    if reponse.status_code != 200:
        return ""
    index = reponse.json().get("abstract_inverted_index")
    if not index:
        return ""
    taille = max(position for positions in index.values() for position in positions) + 1
    mots = [""] * taille
    for mot, positions in index.items():
        for position in positions:
            mots[position] = mot
    return " ".join(mots).strip()


def _charger_nber_rss():
    """Le flux NBER porte l'abstract complet dans description, la page non.

    La page du working paper rend son resume en JavaScript : une lecture du
    HTML n'y trouve que la presentation generique de l'institution. Le flux
    reste la seule source lisible sans navigateur, et c'est celle que la
    collecte quotidienne utilise deja.
    """
    if _cache_nber_rss:
        return _cache_nber_rss
    reponse = requests.get(NBER_RSS, headers=ENTETES, timeout=TIMEOUT)
    reponse.raise_for_status()
    for item in re.findall(r"<item>(.*?)</item>", reponse.text, re.S):
        lien = re.search(r"<link>(.*?)</link>", item, re.S)
        description = re.search(r"<description>(.*?)</description>", item, re.S)
        if lien and description:
            _cache_nber_rss[nettoyer(lien.group(1))] = nettoyer(description.group(1))
    return _cache_nber_rss


def abstract_nber(url):
    numero = re.search(r"/papers/(w\d+)", url)
    if numero:
        texte = abstract_openalex(f"10.3386/{numero.group(1)}")
        if len(texte) > 200:
            return texte
    flux = _charger_nber_rss()
    return flux.get(url, "") or flux.get(url.split("#")[0], "")


def _charger_cepr_rss():
    """cepr.org refuse la lecture directe d'une colonne (403), pas son flux."""
    if _cache_cepr_rss:
        return _cache_cepr_rss
    reponse = requests.get(CEPR_RSS, headers=ENTETES, timeout=TIMEOUT)
    reponse.raise_for_status()
    for item in re.findall(r"<item>(.*?)</item>", reponse.text, re.S):
        lien = re.search(r"<link>(.*?)</link>", item, re.S)
        description = re.search(r"<description>(.*?)</description>", item, re.S)
        if lien and description:
            _cache_cepr_rss[nettoyer(lien.group(1)).rstrip("/")] = nettoyer(
                description.group(1)
            )
    return _cache_cepr_rss


def abstract_cepr(url):
    return _charger_cepr_rss().get(url.rstrip("/"), "")


def abstract_fed(url):
    """La page IFDP annonce son resume par un titre Abstract, sans balise meta."""
    reponse = requests.get(url, headers=ENTETES, timeout=TIMEOUT)
    reponse.raise_for_status()
    texte = nettoyer(reponse.text)
    debut = texte.find("Abstract:")
    if debut < 0:
        return ""
    return texte[debut + len("Abstract:"):].split("Accessible version")[0].strip()[:2500]


def recuperer(url):
    if "arxiv.org" in url:
        return abstract_arxiv(url)
    if "nber.org" in url:
        return abstract_nber(url)
    if "cepr.org" in url:
        return abstract_cepr(url)
    if "federalreserve.gov" in url:
        return abstract_fed(url)
    if "doi.org" in url:
        return abstract_openalex(url.split("doi.org/", 1)[-1]) or abstract_meta(url)
    return abstract_meta(url)


def main():
    from pipeline import regenerer_flux

    flux = json.loads(FLUX.read_text(encoding="utf-8"))
    connus = regenerer_flux.charger_abstracts()
    _, _, sans_abstract = regenerer_flux.trier_pour_rattrapage(flux, connus)
    par_id = {entree["id"]: entree for entree in flux}

    deja = {}
    if SORTIE.exists():
        deja = {item["id"]: item for item in json.loads(SORTIE.read_text(encoding="utf-8"))}

    recoltes = dict(deja)
    for rang, entree in enumerate(sans_abstract, start=1):
        identifiant = entree["id"]
        if identifiant in deja:
            print(f"[{rang}/{len(sans_abstract)}] {identifiant} : deja recolte")
            continue
        url = par_id[identifiant].get("url", "")
        try:
            abstract = recuperer(url)
        except Exception as erreur:
            print(f"[{rang}/{len(sans_abstract)}] {identifiant} : echec, {erreur}", file=sys.stderr)
            continue
        if not abstract or len(abstract) < 200:
            print(f"[{rang}/{len(sans_abstract)}] {identifiant} : abstract trop court, ignore")
            continue
        recoltes[identifiant] = {"id": identifiant, "abstract": abstract}
        print(f"[{rang}/{len(sans_abstract)}] {identifiant} : {len(abstract)} caracteres")
        time.sleep(1)

    SORTIE.write_text(
        json.dumps(list(recoltes.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(recoltes)} abstracts dans {SORTIE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
