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

# Quatre executions, soit environ deux semaines au rythme du lundi et du
# jeudi. Le plancher du signal (pipeline/publish.py, SEUIL_SIGNAL) a rendu
# possible une section vide, ce qu'aucun controle ne voyait : une execution
# peut publier ses neuf items, ne rien signaler, et paraitre en parfaite sante
# puisque nb_publies est le seul chiffre surveille. Deux causes tres
# differentes produisent le meme ecran, une quinzaine calme et un scoring qui
# a cesse de fonctionner.
NB_EXECUTIONS_SANS_SIGNAL = 4


def executions_a_zero_publication(historique, nb_executions):
    if len(historique) < nb_executions:
        return None
    dernieres = historique[-nb_executions:]
    if all(execution.get("nb_publies", 0) == 0 for execution in dernieres):
        return dernieres
    return None


def executions_sans_signal(historique, nb_executions):
    """Dernieres executions n'ayant designe aucun signal, ou None.

    Ne considere que les lignes portant `signal_designe` : celles ecrites
    avant le 17 aout 2026 ne le portent pas, et les traiter comme des absences
    de signal declencherait l'alerte sur du passe qui n'en savait rien.
    """
    renseignees = [e for e in historique if "signal_designe" in e]
    if len(renseignees) < nb_executions:
        return None
    dernieres = renseignees[-nb_executions:]
    if all(execution.get("signal_designe") is False for execution in dernieres):
        return dernieres
    return None


def rapporter_signal(historique):
    """Rapporte l'issue du signal, sans jamais faire echouer le job.

    Informatif la ou l'alerte a zero publication est bloquante, et le choix se
    defend par le taux de fausse alerte. Zero item publie deux fois de suite
    est presque toujours une panne. Une quinzaine sans signal marquant reste
    plausible sur un flux de veille : faire echouer le workflow dessus
    apprendrait a ignorer ses echecs, ce qui coute plus cher que de rater
    l'information. Pour rendre le controle bloquant, remplacer le print par
    sys.exit(1).

    score_max est journalise a chaque execution meme quand tout va bien : le
    plancher a ete fixe le 17 aout 2026 sur une seule semaine de donnees et
    un raisonnement sur la structure du score, jamais sur une distribution
    observee. Ces lignes-la sont la matiere qui permettra de le reviser.
    """
    renseignees = [e for e in historique if "signal_designe" in e]
    if not renseignees:
        return

    derniere = renseignees[-1]
    score_max = derniere.get("score_max")
    print(
        "Signal de la semaine : "
        + ("designe" if derniere.get("signal_designe") else "aucun")
        + f" (meilleur score de la recolte : {score_max if score_max is not None else 'recolte vide'})."
    )

    calmes = executions_sans_signal(renseignees, NB_EXECUTIONS_SANS_SIGNAL)
    if calmes is None:
        return

    print(
        f"A SURVEILLER : les {NB_EXECUTIONS_SANS_SIGNAL} dernieres executions "
        "n'ont designe aucun signal. Une quinzaine calme reste possible, mais "
        "un scoring qui a cesse de fonctionner donnerait le meme resultat."
    )
    for execution in calmes:
        print(f"  - {execution.get('date')} : score_max={execution.get('score_max')}")
    print(
        "Comparer ces score_max au plancher SEUIL_SIGNAL (pipeline/publish.py). "
        "Des maximums qui s'ecrasent sous le plancher execution apres execution "
        "designent le scoring, pas l'actualite : verifier MOTS_CLES_ECO et "
        "MOTS_CLES_IA dans curate.py, et la forme des resumes servis par les "
        "sources. Des maximums qui frolent le plancher sans l'atteindre "
        "designent plutot le plancher lui-meme, a rebaisser."
    )


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
        rapporter_signal(historique)
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
