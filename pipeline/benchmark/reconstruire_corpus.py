"""Reconstruit et fige le corpus de comparaison de La Frontière."""

import argparse
import hashlib
import html
import json
import re
import subprocess
import time
from pathlib import Path
from xml.etree import ElementTree

import requests


SOURCE_COMMIT = "3f406d40d7b9bc8ad7d58895d6984cc2ec33fe51"
SORTIE_DEFAUT = Path(__file__).with_name("corpus.json")
ARXIV_API = "https://export.arxiv.org/api/query"
CEPR_RSS = "https://cepr.org/rss/vox-content"
ENTETES = {"User-Agent": "LaFrontiereBenchmark/1.0 (https://djidonou.com)"}
TIMEOUT = 45
TAILLE_LOT_ARXIV = 25

REPLIS_VOXEU = {
    "https://cepr.org/voxeu/columns/chatgpts-financial-advice-supply-demand-and-life-cycle": {
        "type": "crossref",
        "identifiant": "10.2139/ssrn.6446286",
    },
    "https://cepr.org/voxeu/columns/ai-productivity-and-work-evidence-us-firms": {
        "type": "openalex",
        "identifiant": "10.3386/w34984",
    },
}


def nettoyer_texte_source(texte):
    sans_balises = re.sub(r"<[^>]+>", " ", texte or "")
    return " ".join(html.unescape(sans_balises).split())


def reconstruire_abstract_openalex(index_inverse):
    if not index_inverse:
        return ""
    taille = max(position for positions in index_inverse.values() for position in positions) + 1
    mots = [""] * taille
    for mot, positions in index_inverse.items():
        for position in positions:
            mots[position] = mot
    return " ".join(mots).strip()


def charger_snapshot(git_ref):
    contenu = subprocess.check_output(
        ["git", "show", f"{git_ref}:frontiere/data/flux.json"]
    )
    return json.loads(contenu.decode("utf-8"))


def recuperer_arxiv(identifiants):
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    resultats = {}
    for debut in range(0, len(identifiants), TAILLE_LOT_ARXIV):
        lot = identifiants[debut:debut + TAILLE_LOT_ARXIV]
        reponse = requests.get(
            ARXIV_API,
            params={"id_list": ",".join(lot), "max_results": len(lot)},
            headers=ENTETES,
            timeout=TIMEOUT,
        )
        reponse.raise_for_status()
        racine = ElementTree.fromstring(reponse.content)
        for entree in racine.findall("atom:entry", ns):
            url = entree.findtext("atom:id", default="", namespaces=ns)
            identifiant = url.rsplit("/", 1)[-1]
            abstract = entree.findtext("atom:summary", default="", namespaces=ns)
            resultats[identifiant] = nettoyer_texte_source(abstract)
        if debut + TAILLE_LOT_ARXIV < len(identifiants):
            time.sleep(3)
    return resultats


def recuperer_rss_cepr():
    reponse = requests.get(CEPR_RSS, headers=ENTETES, timeout=TIMEOUT)
    reponse.raise_for_status()
    racine = ElementTree.fromstring(reponse.content)
    resultats = {}
    for entree in racine.findall(".//item"):
        url = (entree.findtext("link") or "").strip()
        abstract = nettoyer_texte_source(entree.findtext("description") or "")
        if url and abstract:
            resultats[url] = abstract
    return resultats


def recuperer_crossref(doi):
    reponse = requests.get(
        f"https://api.crossref.org/works/{doi}",
        headers=ENTETES,
        timeout=TIMEOUT,
    )
    reponse.raise_for_status()
    return nettoyer_texte_source(reponse.json()["message"].get("abstract", ""))


def recuperer_openalex(doi):
    reponse = requests.get(
        f"https://api.openalex.org/works/https://doi.org/{doi}",
        headers=ENTETES,
        timeout=TIMEOUT,
    )
    reponse.raise_for_status()
    return reconstruire_abstract_openalex(
        reponse.json().get("abstract_inverted_index")
    )


def recuperer_voxeu(url, rss):
    if url in rss:
        return rss[url], "CEPR RSS vox-content"
    repli = REPLIS_VOXEU.get(url)
    if not repli:
        raise RuntimeError(f"aucune source d'abstract pour {url}")
    if repli["type"] == "crossref":
        abstract = recuperer_crossref(repli["identifiant"])
        provenance = f"Crossref DOI {repli['identifiant']}"
    else:
        abstract = recuperer_openalex(repli["identifiant"])
        provenance = f"OpenAlex DOI {repli['identifiant']}"
    return abstract, provenance


def construire_corpus(git_ref):
    snapshot = charger_snapshot(git_ref)
    identifiants_arxiv = [
        entree["id"].removeprefix("arxiv-")
        for entree in snapshot
        if entree["id"].startswith("arxiv-")
    ]
    abstracts_arxiv = recuperer_arxiv(identifiants_arxiv)
    rss_cepr = recuperer_rss_cepr()

    items = []
    for entree in snapshot:
        if entree["id"].startswith("arxiv-"):
            identifiant = entree["id"].removeprefix("arxiv-")
            abstract = abstracts_arxiv.get(identifiant, "")
            provenance = f"arXiv API {identifiant}"
        else:
            abstract, provenance = recuperer_voxeu(entree["url"], rss_cepr)
        if not abstract:
            raise RuntimeError(f"abstract manquant pour {entree['id']}")
        items.append({
            "id": entree["id"],
            "titre": entree["titre"],
            "url": entree["url"],
            "source": entree["source"],
            "type": entree["type"],
            "date_publication": entree.get("date_publication"),
            "auteurs": entree.get("auteurs", ""),
            "score": entree.get("score"),
            "abstract": abstract,
            "provenance_abstract": provenance,
        })

    empreinte = hashlib.sha256(
        json.dumps(items, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "source_commit": git_ref,
        "nombre_items": len(items),
        "sha256_items": empreinte,
        "items": items,
    }


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--git-ref", default=SOURCE_COMMIT)
    analyseur.add_argument("--sortie", type=Path, default=SORTIE_DEFAUT)
    arguments = analyseur.parse_args()

    corpus = construire_corpus(arguments.git_ref)
    arguments.sortie.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Corpus écrit : {corpus['nombre_items']} items")
    print(f"SHA-256 : {corpus['sha256_items']}")
    print(arguments.sortie)


if __name__ == "__main__":
    main()
