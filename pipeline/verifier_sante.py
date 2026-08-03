"""Alerte de sante pour La Frontiere.

curate.py journalise chaque execution dans frontiere/data/sante.json (nombre
d'items eligibles, publies, reportes, rejetes). Ce script se lance apres
publish.py et ne verifie qu'une chose : si les deux dernieres executions ont
publie zero item, il sort en erreur pour faire echouer le workflow.

Ce script ne bloque jamais publish.py, qui a deja ecrit avant lui. Il ne fait
qu'alerter, jamais qu'empecher la maintenance normale du flux (fenetre de 90
jours, archives).

Une seule execution a zero publication est normale : une semaine peut
simplement etre creuse, faute de candidats interessants. Deux d'affilee sont
plus probablement le signe d'une panne silencieuse (sources toutes en echec,
mots-cles trop stricts, budget systematiquement epuise) qu'un service
indisponible fait deja echouer bruyamment ailleurs.
"""

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SANTE = Path(__file__).parent.parent / "frontiere" / "data" / "sante.json"
NB_EXECUTIONS_CONSECUTIVES = 2


def executions_a_zero_publication(historique, nb_executions):
    if len(historique) < nb_executions:
        return None
    dernieres = historique[-nb_executions:]
    if all(execution.get("nb_publies", 0) == 0 for execution in dernieres):
        return dernieres
    return None


def main():
    if not SANTE.exists():
        print("Aucun historique de sante trouve, rien a verifier.")
        return

    historique = json.loads(SANTE.read_text(encoding="utf-8"))
    suspectes = executions_a_zero_publication(historique, NB_EXECUTIONS_CONSECUTIVES)

    if suspectes is None:
        derniere = historique[-1] if historique else {}
        print(
            "Sante du flux : ok "
            f"(derniere execution : {derniere.get('nb_publies', '?')} item(s) publie(s))."
        )
        return

    print(
        f"ALERTE : les {NB_EXECUTIONS_CONSECUTIVES} dernieres executions ont "
        "publie zero item. Ce n'est probablement plus une semaine creuse.",
        file=sys.stderr,
    )
    for execution in suspectes:
        print(
            f"  - {execution.get('date')} : "
            f"eligibles={execution.get('nb_eligibles')}, "
            f"reportes={execution.get('nb_reportes')}, "
            f"rejetes_validation={execution.get('nb_rejetes_validation')}, "
            f"fournisseur={execution.get('fournisseur')}",
            file=sys.stderr,
        )
    print(
        "Verifier : sources toutes en echec de collecte (voir "
        "pipeline/_collecte_sante.json genere par collect.py), mots-cles "
        "MOTS_CLES_ECO/MOTS_CLES_IA (collect.py, curate.py) devenus trop "
        "stricts, ou budget d'appels au modele systematiquement epuise "
        "avant la fin du lot.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
