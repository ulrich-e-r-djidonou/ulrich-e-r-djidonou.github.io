"""Collecte multi-sources pour La Frontiere.

Lit pipeline/sources.yaml, interroge chaque source active, et ecrit
pipeline/_candidats_bruts.json (liste d'items bruts, non scores, non dedupliques).

Une source qui echoue (reseau, format inattendu) est loguee et sautee :
le run ne s'interrompt jamais a cause d'une seule source.
"""

import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import feedparser
import requests
import yaml

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ICI = Path(__file__).parent
SOURCES_YAML = ICI / "sources.yaml"
SORTIE = ICI / "_candidats_bruts.json"

MOTS_CLES_ECO = [
    "econom", "labor", "labour", "wage", "market", "policy", "welfare",
    "productiv", "causal", "econometric", "unemployment", "inequality",
    "fiscal", "monetary", "trade", "growth", "finance",
]
MOTS_CLES_IA = [
    "artificial intelligence", "machine learning", "deep learning", "llm",
    "large language model", "neural network", "algorithm", "automation",
    "gpt", "foundation model", "generative ai", "chatbot",
]

TIMEOUT = 20
NAVIGATEUR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 LaFrontiere-Veille/djidonou.com"
    )
}


def contient_mot_cle(texte, mots_cles):
    texte_bas = texte.lower()
    return any(mot in texte_bas for mot in mots_cles)


def dans_fenetre(date_pub, fenetre_jours):
    if date_pub is None:
        return True
    limite = datetime.now(timezone.utc) - timedelta(days=fenetre_jours)
    return date_pub >= limite


def parser_date_rss(entree):
    for champ in ("published_parsed", "updated_parsed"):
        valeur = entree.get(champ)
        if valeur:
            return datetime(*valeur[:6], tzinfo=timezone.utc)
    return None


def collecter_arxiv(source):
    items = []
    categories = source["categories"]
    requete = " OR ".join(f"cat:{c}" for c in categories)
    url = (
        "http://export.arxiv.org/api/query"
        f"?search_query={requete}&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={source.get('max_resultats', 40)}"
    )
    reponse = requests.get(url, timeout=TIMEOUT, headers=NAVIGATEUR)
    reponse.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    racine = ElementTree.fromstring(reponse.content)
    for entree in racine.findall("atom:entry", ns):
        titre = entree.findtext("atom:title", default="", namespaces=ns).strip().replace("\n", " ")
        resume = entree.findtext("atom:summary", default="", namespaces=ns).strip().replace("\n", " ")
        id_arxiv = entree.findtext("atom:id", default="", namespaces=ns).strip()
        publie = entree.findtext("atom:published", default="", namespaces=ns).strip()
        auteurs = [
            a.findtext("atom:name", default="", namespaces=ns)
            for a in entree.findall("atom:author", ns)
        ]
        try:
            date_pub = datetime.fromisoformat(publie.replace("Z", "+00:00"))
        except ValueError:
            date_pub = None

        if not dans_fenetre(date_pub, source.get("fenetre_jours", 30)):
            continue
        if source.get("requiert_mot_cle_eco") and not contient_mot_cle(titre + " " + resume, MOTS_CLES_ECO):
            continue
        if source.get("requiert_mot_cle_ia") and not contient_mot_cle(titre + " " + resume, MOTS_CLES_IA):
            continue

        arxiv_slug = id_arxiv.rsplit("/", 1)[-1]
        items.append({
            "id": f"arxiv-{arxiv_slug}",
            "titre": titre,
            "url": id_arxiv.replace("http://", "https://"),
            "source": source["nom"],
            "type": "papier",
            "date_publication": date_pub.date().isoformat() if date_pub else None,
            "abstract": resume,
            "auteurs": ", ".join(a for a in auteurs if a),
        })
    return items


def collecter_rss(source):
    items = []
    flux = feedparser.parse(source["url"], request_headers=NAVIGATEUR)
    if flux.bozo and not flux.entries:
        raise RuntimeError(f"flux RSS illisible : {flux.bozo_exception}")

    for entree in flux.entries:
        titre = entree.get("title", "").strip()
        resume = re.sub("<[^<]+?>", "", entree.get("summary", "")).strip()
        lien = entree.get("link", "")
        date_pub = parser_date_rss(entree)

        if not dans_fenetre(date_pub, source.get("fenetre_jours", 30)):
            continue
        if source.get("requiert_mot_cle_eco") and not contient_mot_cle(titre + " " + resume, MOTS_CLES_ECO):
            continue
        if source.get("requiert_mot_cle_ia") and not contient_mot_cle(titre + " " + resume, MOTS_CLES_IA):
            continue
        if not lien:
            continue

        items.append({
            "id": f"{source['id']}-{re.sub(r'[^a-zA-Z0-9]+', '-', lien)[-60:]}",
            "titre": titre,
            "url": lien,
            "source": source["nom"],
            "type": "article",
            "date_publication": date_pub.date().isoformat() if date_pub else None,
            "abstract": resume,
            "auteurs": "",
        })
    return items


def collecter_github_commits(source):
    items = []
    depuis = (datetime.now(timezone.utc) - timedelta(days=source.get("fenetre_jours", 30))).isoformat()
    url = (
        f"https://api.github.com/repos/{source['repo']}/commits"
        f"?path={source['fichier']}&since={depuis}"
    )
    reponse = requests.get(url, timeout=TIMEOUT, headers=NAVIGATEUR)
    reponse.raise_for_status()
    for commit in reponse.json():
        sha = commit["sha"][:10]
        message = commit["commit"]["message"].split("\n")[0].strip()
        date_pub = commit["commit"]["author"]["date"][:10]
        items.append({
            "id": f"{source['id']}-{sha}",
            "titre": f"Mise a jour de la liste awesome : {message}",
            "url": f"https://github.com/{source['repo']}/commit/{commit['sha']}",
            "source": source["nom"],
            "type": "annonce",
            "date_publication": date_pub,
            "abstract": message,
            "auteurs": commit["commit"]["author"].get("name", ""),
        })
    return items


COLLECTEURS = {
    "arxiv": collecter_arxiv,
    "rss": collecter_rss,
    "github_commits": collecter_github_commits,
}


def main():
    config = yaml.safe_load(SOURCES_YAML.read_text(encoding="utf-8"))
    tous_les_items = []
    recap = []

    for source in config["sources"]:
        if not source.get("actif", True):
            recap.append((source["id"], "desactive", 0))
            continue
        collecteur = COLLECTEURS.get(source["type"])
        if collecteur is None:
            recap.append((source["id"], f"type inconnu : {source['type']}", 0))
            continue
        try:
            items = collecteur(source)
            tous_les_items.extend(items)
            recap.append((source["id"], "ok", len(items)))
        except Exception as exc:  # une source en echec ne bloque jamais le run
            recap.append((source["id"], f"echec : {exc}", 0))

    SORTIE.write_text(json.dumps(tous_les_items, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Recapitulatif de la collecte :")
    for id_source, statut, nb in recap:
        print(f"  - {id_source} : {statut} ({nb} items)")
    print(f"Total brut : {len(tous_les_items)} items ecrits dans {SORTIE}")


if __name__ == "__main__":
    main()
