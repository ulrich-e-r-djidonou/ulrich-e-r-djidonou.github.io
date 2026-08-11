"""Detecte une source dont l'extraction d'auteurs s'est cassee.

Le 2026-08-11, deux bugs distincts dans collecter_rss (pipeline/collect.py)
ont laisse 8 items sur 45 sans auteur affiche sur La Frontiere, dont un
signale directement par Ulrich. Le code a ete corrige (voir collect.py et
test_collect.py), mais un flux externe peut changer de format a tout moment
sans que personne ne s'en rende compte : ce script est le filet de securite
qui detecte la prochaine fois que ca arrive, plutot que de compter
uniquement sur le fait que le code actuel soit correct aujourd'hui.

Principe : une source qui fournit normalement des auteurs perd RAREMENT un
item isole (une page bloquee, un cas limite) mais perd RAREMENT PAS un item
sur deux. Une source dont 100 % des items du flux courant sont sans auteur
est le signe d'une extraction entierement cassee, exactement le motif des
deux bugs corriges ce jour-la. Une source partiellement incomplete (quelques
items non retrouves, deja documentes au cas par cas) n'est qu'informative.

    python -m pipeline.verifier_auteurs
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
FLUX = RACINE / "frontiere" / "data" / "flux.json"

# Sources dont le flux ne fournit d'auteurs par aucun moyen connu (documente
# egalement dans pipeline/sources.yaml, a cote de la config de la source).
# Une source ici n'est jamais signalee, meme si tous ses items sont sans
# auteur : c'est l'etat normal, pas une regression.
SOURCES_SANS_AUTEURS_CONNUES = {
    "Banque centrale europeenne (BCE), working papers",
}


def regressions_completes(items):
    """Sources (hors liste connue) dont 100% des items sont sans auteur.

    Renvoie {nom_source: nombre_items}, trie par nombre d'items decroissant.
    """
    par_source = defaultdict(list)
    for item in items:
        par_source[item.get("source", "")].append(item)

    resultat = {}
    for source, items_source in par_source.items():
        if source in SOURCES_SANS_AUTEURS_CONNUES:
            continue
        sans_auteur = [i for i in items_source if not i.get("auteurs", "").strip()]
        if sans_auteur and len(sans_auteur) == len(items_source):
            resultat[source] = len(items_source)
    return dict(sorted(resultat.items(), key=lambda kv: kv[1], reverse=True))


def main():
    if not FLUX.exists():
        print(f"{FLUX} introuvable, rien a verifier.")
        return 0

    items = json.loads(FLUX.read_text(encoding="utf-8"))
    total = len(items)
    sans_auteur = sum(1 for i in items if not i.get("auteurs", "").strip())
    print(f"Auteurs : {total - sans_auteur}/{total} items avec auteur renseigne.")

    cassees = regressions_completes(items)
    if not cassees:
        print("Aucune source n'a perdu tous ses auteurs.")
        return 0

    print("\nExtraction d'auteurs probablement cassee pour :")
    for source, nb in cassees.items():
        print(f"  - {source} : {nb}/{nb} item(s) sans auteur")
    print(
        "\nSi c'est attendu (source qui n'a jamais fourni d'auteurs), ajouter "
        "la source a SOURCES_SANS_AUTEURS_CONNUES dans ce fichier et "
        "documenter pourquoi dans pipeline/sources.yaml. Sinon, verifier "
        "collecter_rss dans pipeline/collect.py pour cette source : c'est "
        "exactement le motif des bugs corriges le 2026-08-11."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
