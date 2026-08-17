"""Releve des score_max journalises, pour calibrer le plancher du signal.

SEUIL_SIGNAL a ete fixe a 6 le 17 aout 2026 sur une seule semaine de donnees
et un raisonnement sur la structure du score, jamais sur une distribution
observee. publish.py journalise depuis le meilleur score de chaque recolte
dans frontiere/data/sante.json ; ce script lit ces lignes et dit ce qu'un
autre plancher aurait donne.

Lecture seule, jamais lance par le workflow : c'est un outil qu'on interroge
quand on se demande si le plancher est bien place.

    python -m pipeline.relever_scores_signal

Le carnet ne garde que les 12 dernieres executions (curate.py,
NB_EXECUTIONS_CONSERVEES), soit environ six semaines au rythme du lundi et du
jeudi. Le releve porte donc sur une fenetre courte, et le dit.
"""

import json
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from pipeline.publish import SEUIL_SIGNAL
except ImportError:  # pragma: no cover - depend du mode de lancement
    from publish import SEUIL_SIGNAL

SANTE = Path(__file__).parent.parent / "frontiere" / "data" / "sante.json"

# En deca, la distribution ne dit rien : quatre executions couvrent deux
# semaines, et deux semaines calmes ne sont pas une tendance. Recommander un
# plancher sur si peu reviendrait a habiller une impression en mesure.
MIN_EXECUTIONS_POUR_RECOMMANDER = 8

# Fourchette visee pour la part d'executions designant un signal. Sous le
# plancher bas, la section est vide trop souvent et le message d'exception
# cesse d'etre lu comme tel ; au-dessus du plancher haut, le signal ne
# distingue plus rien puisque presque tout passe.
PART_CIBLE_MIN = 0.40
PART_CIBLE_MAX = 0.85


def scores_releves(historique):
    """Les score_max renseignes, recolte vide exclue.

    Une recolte vide journalise None : elle ne dit rien sur le plancher, seule
    une recolte reelle mesure quelque chose.
    """
    return [
        execution["score_max"]
        for execution in historique
        if execution.get("score_max") is not None
    ]


def part_avec_signal(scores, seuil):
    """Part des executions dont le meilleur score atteint le seuil."""
    if not scores:
        return None
    return sum(1 for score in scores if score >= seuil) / len(scores)


def seuil_recommande(scores, seuil_actuel):
    """Plancher le plus eleve dont la part tombe dans la fourchette visee.

    Le plus eleve, et non le plus proche du centre : a qualite de couverture
    egale, un plancher haut selectionne mieux. Renvoie None si aucun candidat
    ne convient, cas ou le releve se contente de decrire.
    """
    if not scores:
        return None
    candidats = [
        seuil for seuil in range(1, max(scores) + 1)
        if PART_CIBLE_MIN <= part_avec_signal(scores, seuil) <= PART_CIBLE_MAX
    ]
    if not candidats:
        return None
    recommande = max(candidats)
    return None if recommande == seuil_actuel else recommande


def rendre_releve(historique, seuil_actuel=SEUIL_SIGNAL):
    """Texte du releve. Pur : ne lit ni le disque ni l'horloge."""
    scores = scores_releves(historique)
    if not scores:
        return [
            "Aucun score_max journalise pour l'instant.",
            "Le champ existe depuis le 17 aout 2026 : il faut au moins une "
            "execution du pipeline pour qu'il se remplisse.",
        ]

    lignes = [
        f"Plancher actuel : {seuil_actuel}.",
        f"Executions mesurees : {len(scores)}.",
        "",
        "Distribution des meilleurs scores par recolte :",
    ]
    comptes = Counter(scores)
    for score in sorted(comptes, reverse=True):
        part = comptes[score] / len(scores)
        lignes.append(
            f"  score {score} : {comptes[score]} execution(s), {part:.0%}"
        )

    lignes.append("")
    lignes.append("Part d'executions designant un signal, selon le plancher :")
    for seuil in range(1, max(scores) + 1):
        part = part_avec_signal(scores, seuil)
        marque = "  <- actuel" if seuil == seuil_actuel else ""
        lignes.append(f"  plancher {seuil} : {part:.0%}{marque}")

    lignes.append("")
    if len(scores) < MIN_EXECUTIONS_POUR_RECOMMANDER:
        lignes.append(
            f"Trop peu d'executions ({len(scores)}) pour recommander un "
            f"plancher : il en faut {MIN_EXECUTIONS_POUR_RECOMMANDER}, soit "
            "environ un mois. Le releve ci-dessus decrit, il ne conclut pas."
        )
        return lignes

    recommande = seuil_recommande(scores, seuil_actuel)
    part_actuelle = part_avec_signal(scores, seuil_actuel)
    if recommande is None:
        # Deux situations tres differentes se cachent derriere l'absence de
        # recommandation, et les confondre ferait lire « tout va bien » la ou
        # aucun plancher ne convient.
        if PART_CIBLE_MIN <= part_actuelle <= PART_CIBLE_MAX:
            lignes.append(
                f"Rien a changer : le plancher de {seuil_actuel} designe un "
                f"signal {part_actuelle:.0%} du temps, dans la fourchette visee "
                f"({PART_CIBLE_MIN:.0%} a {PART_CIBLE_MAX:.0%})."
            )
        else:
            lignes.append(
                f"Le plancher de {seuil_actuel} designe un signal "
                f"{part_actuelle:.0%} du temps, hors de la fourchette visee "
                f"({PART_CIBLE_MIN:.0%} a {PART_CIBLE_MAX:.0%}), mais aucun "
                "autre plancher n'y tombe non plus : les scores sont trop "
                "concentres pour qu'un seuil les separe utilement. C'est le "
                "score lui-meme qu'il faudrait revoir, pas le plancher."
            )
        return lignes

    sens = "abaisser" if recommande < seuil_actuel else "relever"
    lignes.append(
        f"Piste : {sens} SEUIL_SIGNAL de {seuil_actuel} a {recommande}, ce qui "
        f"ferait passer la part d'executions avec signal de "
        f"{part_actuelle:.0%} a {part_avec_signal(scores, recommande):.0%}."
    )
    lignes.append(
        "A confronter au contenu reel des semaines concernees avant de "
        "trancher : un plancher se juge sur les articles qu'il laisse passer, "
        "pas seulement sur une proportion."
    )
    return lignes


def main():
    if not SANTE.exists():
        print("Aucun historique de sante trouve, rien a relever.")
        return
    historique = json.loads(SANTE.read_text(encoding="utf-8"))
    for ligne in rendre_releve(historique):
        print(ligne)


if __name__ == "__main__":
    main()
