"""Mesure les rejets des validateurs LLM avant leur activation."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pipeline.curate import erreurs_angle, erreurs_resume


def charger_flux(chemin, git_ref):
    if git_ref:
        contenu = subprocess.check_output(
            ["git", "show", f"{git_ref}:frontiere/data/flux.json"]
        )
        return json.loads(contenu.decode("utf-8"))
    return json.loads(chemin.read_text(encoding="utf-8"))


def mesurer(entrees):
    sorties = [entree for entree in entrees if entree.get("llm")]
    controles = {
        "formule_repetitive": 0,
        "resume_nombre_phrases": 0,
        "caracteres_non_latins": 0,
        "angle_nombre_phrases": 0,
        "anglais_residuel": 0,
        "ponctuation_finale": 0,
        "au_moins_un_echec": 0,
        "echec_hors_formule": 0,
    }

    for entree in sorties:
        erreurs_du_resume = set(erreurs_resume(entree.get("resume_fr", "")))
        erreurs_de_angle = set(erreurs_angle(entree.get("angle_eco", "")))
        formule = "formule_stereotypee" in erreurs_de_angle
        hors_formule = erreurs_du_resume | (erreurs_de_angle - {"formule_stereotypee"})

        controles["formule_repetitive"] += formule
        controles["resume_nombre_phrases"] += "nombre_phrases" in erreurs_du_resume
        controles["caracteres_non_latins"] += (
            "caracteres_non_latins" in erreurs_du_resume
            or "caracteres_non_latins" in erreurs_de_angle
        )
        controles["angle_nombre_phrases"] += "nombre_phrases" in erreurs_de_angle
        controles["anglais_residuel"] += "anglais_residuel" in erreurs_du_resume
        controles["ponctuation_finale"] += "ponctuation_finale" in erreurs_du_resume
        controles["au_moins_un_echec"] += bool(erreurs_du_resume or erreurs_de_angle)
        controles["echec_hors_formule"] += bool(hors_formule)

    return len(sorties), controles


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument(
        "chemin",
        nargs="?",
        type=Path,
        default=Path("frontiere/data/flux.json"),
    )
    analyseur.add_argument("--git-ref")
    analyseur.add_argument("--seuil-alerte", type=float, default=20.0)
    arguments = analyseur.parse_args()

    total, controles = mesurer(charger_flux(arguments.chemin, arguments.git_ref))
    print(f"Sorties LLM mesurées : {total}")
    for controle, echecs in controles.items():
        taux = (echecs / total * 100) if total else 0.0
        print(f"{controle} : {echecs}/{total} ({taux:.1f} %)")

    taux_hors_formule = (
        controles["echec_hors_formule"] / total * 100 if total else 0.0
    )
    if taux_hors_formule > arguments.seuil_alerte:
        print(
            f"ALERTE : le taux hors formule dépasse {arguments.seuil_alerte:.1f} %."
        )
        return 2
    print(
        f"Seuil respecté : le taux hors formule reste sous {arguments.seuil_alerte:.1f} %."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
