"""Joint les notes humaines a la cle des modeles et rend le classement.

L'aveugle n'est leve qu'ici, une fois les notes figees.

    python -m pipeline.benchmark.depouiller_evaluation notes_aveugle.csv
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ICI = Path(__file__).parent
CLE = ICI / "cle_evaluation_aveugle.json"


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("notes", type=Path)
    arguments = analyseur.parse_args()

    cle = json.loads(CLE.read_text(encoding="utf-8"))
    par_modele = {}
    manquantes = 0

    with arguments.notes.open(encoding="utf-8-sig", newline="") as fichier:
        for ligne in csv.DictReader(fichier):
            note = (ligne.get("note_humaine_1_5") or "").strip()
            if not note:
                manquantes += 1
                continue
            correspondance = cle.get(ligne["item"], {}).get(ligne["option"])
            if not correspondance:
                print(
                    f"Item {ligne['item']} option {ligne['option']} absent de la cle.",
                    file=sys.stderr,
                )
                continue
            par_modele.setdefault(correspondance["modele"], []).append(float(note))

    if not par_modele:
        print("Aucune note exploitable.", file=sys.stderr)
        return 1

    print(f"{'Modele':<14} {'Notes':>6} {'Moyenne':>8} {'Mediane':>8}  Distribution")
    classement = sorted(
        par_modele.items(), key=lambda couple: statistics.fmean(couple[1]), reverse=True
    )
    for modele, notes in classement:
        distribution = " ".join(
            f"{valeur}:{notes.count(valeur)}" for valeur in (1.0, 2.0, 3.0, 4.0, 5.0)
        )
        print(
            f"{modele:<14} {len(notes):>6} {statistics.fmean(notes):>8.2f} "
            f"{statistics.median(notes):>8.1f}  {distribution}"
        )

    if manquantes:
        print(f"\n{manquantes} version(s) non notee(s), exclues du calcul.")

    effectifs = {len(notes) for notes in par_modele.values()}
    if len(effectifs) > 1:
        print(
            "Attention : les modeles n'ont pas le meme nombre de notes, "
            "la comparaison est bancale."
        )
    plus_petit = min(len(notes) for notes in par_modele.values())
    if plus_petit < 10:
        print(
            f"Echantillon de {plus_petit} notes par modele : lecture indicative, "
            "pas un ecart mesure."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
