"""Collecte multi-sources pour La Frontiere.

Lit pipeline/sources.yaml, interroge chaque source active, et ecrit
pipeline/_candidats_bruts.json (liste d'items bruts, non scores, non dedupliques).

Une source qui echoue (reseau, format inattendu) est loguee et sautee :
le run ne s'interrompt jamais a cause d'une seule source.
"""

import html
import io
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
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
SORTIE_SANTE = ICI / "_collecte_sante.json"

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

# La plupart des entrees ci-dessus sont des racines volontairement tronquees :
# « econom » doit attraper « macroeconomics », donc la correspondance se fait
# par sous-chaine. Quelques acronymes ne le supportent pas : « llm » se trouve
# dans « enrollment », ce qui classait tout papier sur la scolarisation parmi
# les travaux sur les grands modeles de langage. Ceux-la exigent un debut de
# mot. « gpt » n'est pas du lot : aucun mot anglais ne le contient, et
# l'exiger en debut de mot ferait perdre « ChatGPT ».
MOTS_CLES_DEBUT_DE_MOT = {"llm"}
_MOTIFS_DEBUT_DE_MOT = {
    mot: re.compile(rf"\b{re.escape(mot)}", re.IGNORECASE)
    for mot in MOTS_CLES_DEBUT_DE_MOT
}

TIMEOUT = 20
NAVIGATEUR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 LaFrontiere-Veille/djidonou.com"
    )
}


def mot_cle_present(texte_bas, mot):
    motif = _MOTIFS_DEBUT_DE_MOT.get(mot)
    if motif is not None:
        return bool(motif.search(texte_bas))
    return mot in texte_bas


def contient_mot_cle(texte, mots_cles):
    texte_bas = texte.lower()
    return any(mot_cle_present(texte_bas, mot) for mot in mots_cles)


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


def separer_titre_auteurs(titre, separateur):
    """NBER accole les auteurs au titre : « Titre -- by Alice, Bob »."""
    if not separateur or separateur not in titre:
        return titre, ""
    partie_titre, _, partie_auteurs = titre.partition(separateur)
    return partie_titre.strip(), partie_auteurs.strip()


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
        titre, auteurs = separer_titre_auteurs(titre, source.get("separateur_auteurs"))

        if date_pub is None and source.get("date_repli") == "collecte":
            # Le flux « new » de NBER ne porte aucune date. Les items y sont
            # par construction ceux de la semaine : la date de collecte est
            # une approximation assumee, pas une date de publication reelle.
            date_pub = datetime.now(timezone.utc)

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
            "type": source.get("type_item", "article"),
            "date_publication": date_pub.date().isoformat() if date_pub else None,
            "abstract": resume,
            "auteurs": auteurs,
        })
    return items


CROSSREF_API = "https://api.crossref.org/works"


def nettoyer_abstract_jats(brut):
    """Crossref sert les abstracts en JATS : on retire balises et entites.

    Le titre interne « Abstract » est supprime en premier, sinon il se
    retrouve colle au premier mot du texte.
    """
    if not brut:
        return ""
    texte = re.sub(r"<jats:title>.*?</jats:title>", " ", brut, flags=re.DOTALL | re.IGNORECASE)
    texte = re.sub(r"<[^>]+>", " ", texte)
    texte = html.unescape(texte)
    return re.sub(r"\s+", " ", texte).strip()


def date_crossref(item, champs=("published", "issued", "created")):
    """Renvoie la premiere date exploitable, ou None si aucune n'est complete.

    Crossref accepte des dates partielles. Une date reduite a l'annee, ce
    que deposent beaucoup de preprints, ne permet ni la fenetre glissante ni
    le tri : elle est traitee comme absente.
    """
    for champ in champs:
        parties = (item.get(champ) or {}).get("date-parts") or [[]]
        parties = parties[0]
        if len(parties) >= 3:
            try:
                return date(parties[0], parties[1], parties[2])
            except (TypeError, ValueError):
                continue
        if len(parties) == 2:
            try:
                return date(parties[0], parties[1], 1)
            except (TypeError, ValueError):
                continue
    return None


def collecter_crossref(source):
    """Interroge Crossref par ISSN (revues) ou par prefixe DOI (depots).

    L'axe temporel differe selon la source : une revue se date par sa
    publication, un depot de preprints par son enregistrement, seule date
    fiable quand le champ « published » est reduit a l'annee.
    """
    items = []
    axe = source.get("axe_date", "publication")
    champ_filtre = "from-created-date" if axe == "depot" else "from-pub-date"
    tri = "created" if axe == "depot" else "published"

    depuis = date.today() - timedelta(days=source.get("fenetre_jours", 60))
    filtres = [f"{champ_filtre}:{depuis.isoformat()}"]
    for issn in source.get("issn", []):
        filtres.append(f"issn:{issn}")
    if source.get("prefixe_doi"):
        filtres.append(f"prefix:{source['prefixe_doi']}")

    parametres = {
        "filter": ",".join(filtres),
        "sort": tri,
        "order": "desc",
        "rows": source.get("max_resultats", 60),
        "select": "DOI,title,abstract,author,published,issued,created,container-title",
        # Crossref sert plus vite et plus stablement les clients identifies.
        "mailto": source.get("contact", "contact@djidonou.com"),
    }
    reponse = requests.get(CROSSREF_API, params=parametres, timeout=TIMEOUT * 3, headers=NAVIGATEUR)
    reponse.raise_for_status()

    for item in reponse.json()["message"]["items"]:
        titre = " ".join((item.get("title") or [""])[0].split())
        resume = nettoyer_abstract_jats(item.get("abstract"))
        doi = item.get("DOI", "")
        if not titre or not doi:
            continue
        # Sans abstract, la redaction n'a rien a resumer et le score ne
        # porterait que sur le titre : l'item est ecarte a la collecte.
        if not resume:
            continue

        champs_date = ("created", "published", "issued") if axe == "depot" else ("published", "issued", "created")
        date_pub = date_crossref(item, champs_date)
        if date_pub and not dans_fenetre(
            datetime.combine(date_pub, datetime.min.time(), tzinfo=timezone.utc),
            source.get("fenetre_jours", 60),
        ):
            continue
        if source.get("requiert_mot_cle_eco") and not contient_mot_cle(titre + " " + resume, MOTS_CLES_ECO):
            continue
        if source.get("requiert_mot_cle_ia") and not contient_mot_cle(titre + " " + resume, MOTS_CLES_IA):
            continue

        auteurs = ", ".join(
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in item.get("author", [])
        ).strip(", ")

        items.append({
            "id": f"{source['id']}-{re.sub(r'[^a-zA-Z0-9]+', '-', doi)}",
            "titre": titre,
            "url": f"https://doi.org/{doi}",
            "source": (item.get("container-title") or [source["nom"]])[0] or source["nom"],
            "type": source.get("type_item", "papier"),
            "date_publication": date_pub.isoformat() if date_pub else None,
            "abstract": resume,
            "auteurs": auteurs,
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
    "crossref": collecter_crossref,
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

    actives = [ligne for ligne in recap if ligne[1] != "desactive"]
    sante = {
        "total_brut": len(tous_les_items),
        "sources": [
            {"id": id_source, "statut": statut, "items": nb}
            for id_source, statut, nb in recap
        ],
        "sources_actives": len(actives),
        "sources_en_echec": sum(1 for ligne in actives if ligne[1].startswith("echec")),
    }
    SORTIE_SANTE.write_text(json.dumps(sante, ensure_ascii=False, indent=2), encoding="utf-8")

    print("Recapitulatif de la collecte :")
    for id_source, statut, nb in recap:
        print(f"  - {id_source} : {statut} ({nb} items)")
    print(f"Total brut : {len(tous_les_items)} items ecrits dans {SORTIE}")


if __name__ == "__main__":
    main()
