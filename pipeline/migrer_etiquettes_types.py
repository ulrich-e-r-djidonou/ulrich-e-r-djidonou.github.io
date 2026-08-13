"""Reattribue l'etiquette `type` des entrees deja publiees.

Corriger pipeline/sources.yaml (2026-08-12) ne vaut que pour les collectes
futures. Les entrees deja ecrites dans frontiere/data/flux.json et dans les
archives mensuelles gardent l'etiquette produite le jour de leur collecte,
parfois fausse : les working papers de la Reserve federale et de la Banque
centrale europeenne etaient etiquetes « article », et les revues a comite de
lecture de l'American Economic Association « papier ».

Ce module reecrit ces etiquettes en repartant du nom de la source, seule
information fiable presente dans chaque entree.

SIMULATION PAR DEFAUT. Sans argument, rien n'est ecrit : le rapport liste ce
qui changerait. L'ecriture demande --appliquer, explicitement, parce qu'il
s'agit de reecrire des donnees deja publiees.

    python -m pipeline.migrer_etiquettes_types              # simulation
    python -m pipeline.migrer_etiquettes_types --appliquer  # ecriture

Les entrees dont la source n'est pas reconnue sont laissees intactes et
signalees : mieux vaut une etiquette ancienne qu'une etiquette inventee.
"""

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).parent.parent
DONNEES = RACINE / "frontiere" / "data"
ARCHIVES = DONNEES / "archives"

# Correspondance nom de source vers etiquette, alignee sur la convention
# documentee en tete de pipeline/sources.yaml. Les noms sont ceux ecrits dans
# le champ `source` des entrees, pas les identifiants de sources.yaml.
ETIQUETTE_PAR_SOURCE = {
    "arXiv econ.EM / econ.GN": "papier",
    "arXiv cs.LG / cs.CL / stat.ML (filtre economie)": "papier",
    "NBER, nouveaux working papers": "papier",
    "Fonds monetaire international (FMI), working papers": "papier",
    "SSRN, preprints": "papier",
    "Reserve federale americaine (Fed), working papers": "papier",
    "Banque centrale europeenne (BCE), working papers": "papier",
    "VoxEU / CEPR": "article",
    # Arbitrage rendu le 12 aout 2026. Le flux « publications » de la Banque du
    # Canada avait ete decrit comme melangeant notes analytiques et documents de
    # travail ; sa lecture montre qu'il n'en contient aucun. Il ne sert que des
    # publications institutionnelles, d'ou « article ».
    "Banque du Canada, publications": "article",
}

# Les revues de l'AEA arrivent sous leur nom de revue, pas sous le nom de la
# source : le collecteur Crossref ecrit le titre du journal. Toutes sont des
# revues a comite de lecture.
REVUES_AEA = {
    "American Economic Review",
    "American Economic Review: Insights",
    "Journal of Economic Perspectives",
    "Journal of Economic Literature",
    "American Economic Journal: Applied Economics",
    "American Economic Journal: Macroeconomics",
    "American Economic Journal: Economic Policy",
    "American Economic Journal: Microeconomics",
}

# Sources dont l'etiquette n'est pas tranchee. Leurs entrees sont rapportees
# comme non reconnues plutot que reetiquetees a l'aveugle : mieux vaut une
# etiquette ancienne qu'une etiquette inventee. Vide depuis l'arbitrage du
# 12 aout 2026 sur la Banque du Canada.
SOURCES_SANS_DECISION = set()


def etiquette_attendue(source):
    """Renvoie l'etiquette due a une source, ou None si indecidable."""
    if source in REVUES_AEA:
        return "article"
    return ETIQUETTE_PAR_SOURCE.get(source)


def analyser(entrees):
    """Renvoie (changements, non_reconnues) sans rien modifier.

    changements : liste de (titre, source, avant, apres).
    non_reconnues : ensemble des noms de sources sans regle.
    """
    changements = []
    non_reconnues = set()
    for entree in entrees:
        source = entree.get("source", "")
        attendue = etiquette_attendue(source)
        if attendue is None:
            non_reconnues.add(source)
            continue
        actuelle = entree.get("type")
        if actuelle != attendue:
            changements.append(
                (entree.get("titre", "(sans titre)"), source, actuelle, attendue)
            )
    return changements, non_reconnues


def appliquer(entrees):
    """Reecrit les etiquettes en place. Renvoie le nombre de modifications."""
    modifiees = 0
    for entree in entrees:
        attendue = etiquette_attendue(entree.get("source", ""))
        if attendue is not None and entree.get("type") != attendue:
            entree["type"] = attendue
            modifiees += 1
    return modifiees


def fichiers_a_traiter():
    fichiers = [DONNEES / "flux.json"]
    fichiers.extend(sorted(ARCHIVES.glob("*.json")))
    return [f for f in fichiers if f.exists()]


def main():
    # Reconfiguration ici et non au niveau du module : remplacer sys.stdout a
    # l'import enveloppait une seconde fois le flux deja enveloppe par
    # collect.py, et la destruction de l'enveloppe intermediaire fermait le
    # tampon partage. La suite de tests tombait alors en « I/O operation on
    # closed file » des qu'un autre module importe ensuite appelait print.
    # reconfigure() modifie le flux en place, sans creer d'objet a detruire.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    analyse = argparse.ArgumentParser(description=__doc__)
    analyse.add_argument(
        "--appliquer",
        action="store_true",
        help="ecrit les fichiers ; sans ce drapeau, simulation seule",
    )
    options = analyse.parse_args()

    total_changements = 0
    toutes_non_reconnues = set()

    for chemin in fichiers_a_traiter():
        entrees = json.loads(chemin.read_text(encoding="utf-8"))
        changements, non_reconnues = analyser(entrees)
        toutes_non_reconnues |= non_reconnues
        total_changements += len(changements)

        relatif = chemin.relative_to(RACINE)
        if not changements:
            print(f"{relatif} : rien a changer ({len(entrees)} entrees).")
            continue

        print(f"\n{relatif} : {len(changements)} entree(s) a reetiqueter")
        for titre, source, avant, apres in changements:
            court = titre if len(titre) <= 70 else titre[:67] + "..."
            print(f"  {avant} -> {apres}  [{source}]")
            print(f"      {court}")

        if options.appliquer:
            appliquer(entrees)
            contenu = json.dumps(entrees, ensure_ascii=False, indent=2)
            json.loads(contenu)  # validation avant ecriture
            chemin.write_text(contenu, encoding="utf-8")

    if toutes_non_reconnues:
        print("\nSources laissees intactes, faute de regle :")
        for source in sorted(toutes_non_reconnues):
            note = " (en attente d'arbitrage)" if source in SOURCES_SANS_DECISION else ""
            print(f"  {source}{note}")

    print(f"\nTotal : {total_changements} entree(s) concernee(s).")
    if options.appliquer:
        print("Fichiers reecrits. Relire le diff avant de committer.")
    else:
        print("Simulation : aucun fichier modifie. Relancer avec --appliquer pour ecrire.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
