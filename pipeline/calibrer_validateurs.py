"""Mesure les rejets des validateurs LLM avant leur activation."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from pipeline.curate import (
    erreurs_angle,
    erreurs_angle_en,
    erreurs_resume,
    erreurs_resume_en,
)


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


def mesurer_en(entrees):
    sorties_en = [
        entree for entree in entrees
        if entree.get("resume_en") or entree.get("angle_eco_en")
    ]
    controles_en = {
        "resume_en_nombre_phrases": 0,
        "resume_en_ponctuation": 0,
        "angle_en_nombre_phrases": 0,
        "formule_stereotypee_en": 0,
        "premiere_personne_en": 0,
        "tiret_cadratin_en": 0,
        "francais_residuel_en": 0,
        "caracteres_non_latins_en": 0,
        "au_moins_un_echec_en": 0,
    }

    for entree in sorties_en:
        err_res = (
            set(erreurs_resume_en(entree.get("resume_en", "")))
            if entree.get("resume_en")
            else set()
        )
        err_ang = (
            set(erreurs_angle_en(entree.get("angle_eco_en", "")))
            if entree.get("angle_eco_en")
            else set()
        )
        controles_en["resume_en_nombre_phrases"] += "nombre_phrases" in err_res
        controles_en["resume_en_ponctuation"] += "ponctuation_finale" in err_res
        controles_en["angle_en_nombre_phrases"] += "nombre_phrases" in err_ang
        controles_en["formule_stereotypee_en"] += "formule_stereotypee" in err_ang
        controles_en["premiere_personne_en"] += bool(
            "premiere_personne" in err_res or "premiere_personne" in err_ang
        )
        controles_en["tiret_cadratin_en"] += bool(
            "tiret_cadratin" in err_res or "tiret_cadratin" in err_ang
        )
        controles_en["francais_residuel_en"] += bool(
            "francais_residuel" in err_res or "francais_residuel" in err_ang
        )
        controles_en["caracteres_non_latins_en"] += bool(
            "caracteres_non_latins" in err_res or "caracteres_non_latins" in err_ang
        )
        controles_en["au_moins_un_echec_en"] += bool(err_res or err_ang)

    return len(sorties_en), controles_en


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
    analyseur.add_argument(
        "--rapport-seul",
        action="store_true",
        help=(
            "mesure sans faire echouer la commande. Utile sur un flux qui "
            "contient encore des textes rediges avant les validateurs actuels : "
            "leur taux de rejet ne dit rien de la calibration."
        ),
    )
    arguments = analyseur.parse_args()

    entrees = charger_flux(arguments.chemin, arguments.git_ref)
    total, controles = mesurer(entrees)
    print(f"Sorties LLM mesurées (français) : {total}")
    for controle, echecs in controles.items():
        taux = (echecs / total * 100) if total else 0.0
        print(f"{controle} : {echecs}/{total} ({taux:.1f} %)")

    total_en, controles_en = mesurer_en(entrees)
    if total_en:
        print()
        print(f"Sorties LLM mesurées (anglais) : {total_en}")
        for controle, echecs in controles_en.items():
            taux = (echecs / total_en * 100) if total_en else 0.0
            print(f"{controle} : {echecs}/{total_en} ({taux:.1f} %)")

    taux_hors_formule = (
        controles["echec_hors_formule"] / total * 100 if total else 0.0
    )
    if taux_hors_formule > arguments.seuil_alerte:
        print(
            f"ALERTE : le taux hors formule dépasse {arguments.seuil_alerte:.1f} %."
        )
        return 0 if arguments.rapport_seul else 2
    print(
        f"Seuil respecté : le taux hors formule reste sous {arguments.seuil_alerte:.1f} %."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
