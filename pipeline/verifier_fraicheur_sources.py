"""Signale les sources configurees qui ne produisent plus rien.

Une source peut mourir sans bruit. Son flux repond toujours 200, son XML
reste valide, la collecte ne leve aucune erreur : elle renvoie simplement
zero entree, run apres run. Rien dans le pipeline ne distingue « cette
source n'a rien publie cette semaine » de « cette source est morte depuis
huit mois ».

Le cas est reel. Le 12 aout 2026, l'ajout de la source des notes analytiques
du personnel de la Banque du Canada a montre un flux parfaitement lisible,
dix entrees, dont la plus recente datait du 12 decembre 2025. La meme
verification a montre que le flux « publications » de la Banque n'avait
jamais rien fait entrer dans la veille depuis son ajout, son filtre de
mots-cles ecartant tout, sans que personne en soit informe.

Ce module rend visible cette difference. Il ne remplace aucun controle : il
rapporte, il ne bloque pas.

    python -m pipeline.verifier_fraicheur_sources           # rapport complet
    python -m pipeline.verifier_fraicheur_sources --muettes # les muettes seules
    python -m pipeline.verifier_fraicheur_sources --strict  # code 1 si muette

Le mode par defaut sort toujours 0 : ce constat est informatif, comme
calibrer_validateurs. Une source silencieuse est un signal a regarder, pas
une raison de faire echouer une CI.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

import yaml

from pipeline import collect

# Au-dela de ce silence, une source cesse d'etre « calme » pour devenir
# suspecte. Trois mois laissent passer les rythmes lents, une revue
# trimestrielle ou un institut qui ne publie qu'a chaque saison, sans laisser
# une source reellement morte se fondre dans le decor pendant un an.
SEUIL_DORMANCE_JOURS = 90


def diagnostic(nb_items, nb_dans_fenetre, nb_retenus, jours_depuis_derniere):
    """Classe une source a partir de ses seuls compteurs.

    Volontairement sans reseau : la collecte est faite par l'appelant, ce
    qui rend ce classement testable sans dependre de l'etat d'un serveur
    tiers un jour donne.

    Renvoie un couple (etat, explication).
    """
    # Teste en premier : une source qui fait entrer des elements dans la veille
    # est active, quoi que disent ses compteurs intermediaires. Le flux « new »
    # de NBER ne porte aucune date et s'appuie sur date_repli ; le compter hors
    # fenetre le declarait muet alors qu'il alimentait bel et bien la veille.
    if nb_retenus > 0:
        return ("ACTIVE", f"{nb_retenus} entree(s) retenue(s)")

    # nb_items vaut None quand les compteurs avant filtrage ne sont pas
    # observables : les collecteurs arxiv, crossref et github_commits filtrent
    # dans la requete elle-meme. Dire « le flux est vide » serait alors une
    # affirmation que rien n'etaye, et c'est exactement ce que ce module
    # reproche au reste du pipeline.
    if nb_items is None:
        return (
            "SANS RETOUR",
            "aucune entree retenue ; ce type de collecteur ne permet pas de "
            "distinguer un flux tari de filtres trop etroits",
        )

    if nb_items == 0:
        return ("VIDE", "le flux repond mais ne contient aucune entree")

    if jours_depuis_derniere is not None and jours_depuis_derniere > SEUIL_DORMANCE_JOURS:
        return (
            "DORMANTE",
            f"derniere publication il y a {jours_depuis_derniere} jours",
        )

    if nb_dans_fenetre == 0:
        return ("HORS FENETRE", "aucune entree assez recente pour la fenetre configuree")

    return (
        "FILTREE",
        f"{nb_dans_fenetre} entree(s) recente(s), toutes ecartees par les filtres",
    )


def est_muette(etat):
    """Vrai si l'etat traduit une source qui n'alimente pas la veille."""
    return etat != "ACTIVE"


def charger_sources():
    donnees = yaml.safe_load(collect.SOURCES_YAML.read_text(encoding="utf-8"))
    return [s for s in donnees.get("sources", []) if s.get("actif")]


def compteurs_rss(source, maintenant):
    """Mesure les trois compteurs d'un flux RSS. Fait du reseau.

    Les collecteurs de collect.py ne renvoient que les entrees retenues :
    ils ne permettent pas de distinguer « le flux est vide » de « les filtres
    ont tout ecarte ». On relit donc le flux ici pour compter avant filtrage,
    ce qui est precisement l'information qui manquait.
    """
    import feedparser
    import requests

    reponse = requests.get(source["url"], timeout=collect.TIMEOUT, headers=collect.NAVIGATEUR)
    reponse.raise_for_status()
    flux = feedparser.parse(reponse.content)

    dates = [d for d in (collect.parser_date_rss(e) for e in flux.entries) if d]
    fenetre = source.get("fenetre_jours", 30)
    nb_dans_fenetre = sum(1 for d in dates if collect.dans_fenetre(d, fenetre))

    jours = None
    if dates:
        plus_recente = max(dates)
        if plus_recente.tzinfo is None:
            plus_recente = plus_recente.replace(tzinfo=timezone.utc)
        jours = (maintenant - plus_recente).days

    return len(flux.entries), nb_dans_fenetre, jours


def sonder(source, maintenant=None):
    """Interroge une source et renvoie (etat, explication). Fait du reseau."""
    maintenant = maintenant or datetime.now(timezone.utc)
    collecteur = getattr(collect, f"collecter_{source['type']}", None)
    if collecteur is None:
        return ("INCONNUE", f"aucun collecteur pour le type '{source['type']}'")

    try:
        retenus = collecteur(source)
        if source["type"] == "rss":
            nb_items, nb_dans_fenetre, jours = compteurs_rss(source, maintenant)
        else:
            # Les autres collecteurs (arxiv, crossref, github_commits) filtrent
            # dans la requete plutot qu'apres coup : leurs compteurs
            # intermediaires n'existent pas. None dit « non observable », ce
            # qui n'est pas la meme chose que zero.
            nb_items = None
            nb_dans_fenetre = 0
            jours = None
    except Exception as erreur:  # noqa: BLE001 - on rapporte, on ne propage pas
        return ("ECHEC", f"{type(erreur).__name__}: {erreur}")

    return diagnostic(
        nb_items=nb_items,
        nb_dans_fenetre=nb_dans_fenetre,
        nb_retenus=len(retenus),
        jours_depuis_derniere=jours,
    )


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    analyse = argparse.ArgumentParser(description=__doc__)
    analyse.add_argument(
        "--muettes", action="store_true", help="n'afficher que les sources muettes"
    )
    analyse.add_argument(
        "--strict",
        action="store_true",
        help="sortir en code 1 si au moins une source est muette",
    )
    options = analyse.parse_args(argv)

    muettes = []
    for source in charger_sources():
        etat, explication = sonder(source)
        if est_muette(etat):
            muettes.append((source["id"], etat, explication))
            print(f"{etat:<12} {source['id']:<24} {explication}")
        elif not options.muettes:
            print(f"{etat:<12} {source['id']:<24} {explication}")

    if not muettes:
        print("\nToutes les sources actives alimentent la veille.")
        return 0

    print(f"\n{len(muettes)} source(s) muette(s) sur les actives.")
    print("Une source muette n'est pas forcement a retirer : verifier d'abord")
    print("si son flux a change d'adresse, puis si ses filtres sont trop etroits.")
    return 1 if options.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
