"""Génère le rapport comparatif et l'échantillon d'évaluation aveugle."""

import argparse
import csv
import json
import random
from pathlib import Path


ICI = Path(__file__).parent
RESULTATS_DEFAUT = ICI / "resultats.json"
CORPUS_DEFAUT = ICI / "corpus.json"
RAPPORT_DEFAUT = ICI / "rapport_comparatif.md"
EVALUATION_DEFAUT = ICI / "evaluation_aveugle.csv"
CLE_DEFAUT = ICI / "cle_evaluation_aveugle.json"


def calculer_metriques(resultats, modeles):
    metriques = {}
    for modele in modeles:
        compte = {
            "items": 0,
            "resume_nombre_phrases": 0,
            "caracteres_non_latins": 0,
            "anglais_residuel": 0,
            "ponctuation_finale": 0,
            "angle_nombre_phrases": 0,
            "formule_stereotypee": 0,
            "non_publiables": 0,
            "reprises": 0,
            "duree_secondes": 0.0,
        }
        for modeles_item in resultats["items"].values():
            evaluation = modeles_item.get(modele)
            if not evaluation:
                continue
            compte["items"] += 1
            resume = evaluation["resume"]
            angle = evaluation["angle"]
            erreurs_resume = set(resume["essais"][0]["erreurs"])
            erreurs_angle = set(angle["essais"][0]["erreurs"])
            compte["resume_nombre_phrases"] += "nombre_phrases" in erreurs_resume
            compte["caracteres_non_latins"] += (
                "caracteres_non_latins" in erreurs_resume
                or "caracteres_non_latins" in erreurs_angle
            )
            compte["anglais_residuel"] += "anglais_residuel" in erreurs_resume
            compte["ponctuation_finale"] += "ponctuation_finale" in erreurs_resume
            compte["angle_nombre_phrases"] += "nombre_phrases" in erreurs_angle
            compte["formule_stereotypee"] += "formule_stereotypee" in erreurs_angle
            compte["non_publiables"] += not evaluation["publiable"]
            compte["reprises"] += (len(resume["essais"]) - 1) + (len(angle["essais"]) - 1)
            compte["duree_secondes"] += sum(
                essai["duree_secondes"]
                for champ in (resume, angle)
                for essai in champ["essais"]
            )
        compte["duree_secondes"] = round(compte["duree_secondes"], 3)
        metriques[modele] = compte
    return metriques


def taux(nombre, total):
    return f"{(nombre / total * 100 if total else 0):.1f} %"


def generer_evaluation(corpus, resultats, modeles, chemin_csv, chemin_cle):
    titres = {item["id"]: item["titre"] for item in corpus["items"]}
    admissibles = [
        identifiant
        for identifiant, evaluations in resultats["items"].items()
        if all(
            modele in evaluations and evaluations[modele]["publiable"]
            for modele in modeles
        )
    ]
    if len(admissibles) < 10:
        raise RuntimeError("moins de 10 items sont publiables par les trois modèles")

    aleatoire = random.Random(20260802)
    echantillon = aleatoire.sample(sorted(admissibles), 10)
    cle = {}
    with chemin_csv.open("w", encoding="utf-8-sig", newline="") as fichier:
        colonnes = [
            "item", "option", "titre", "resume_fr", "angle_eco",
            "note_humaine_1_5", "commentaire",
        ]
        ecrivain = csv.DictWriter(fichier, fieldnames=colonnes)
        ecrivain.writeheader()
        for numero, identifiant in enumerate(echantillon, start=1):
            ordre = list(modeles)
            aleatoire.shuffle(ordre)
            code_item = f"E{numero:02d}"
            cle[code_item] = {}
            for option, modele in zip(("A", "B", "C"), ordre):
                evaluation = resultats["items"][identifiant][modele]
                cle[code_item][option] = {"modele": modele, "id": identifiant}
                ecrivain.writerow({
                    "item": code_item,
                    "option": option,
                    "titre": titres[identifiant],
                    "resume_fr": evaluation["resume"]["texte_final"],
                    "angle_eco": evaluation["angle"]["texte_final"],
                    "note_humaine_1_5": "",
                    "commentaire": "",
                })
    chemin_cle.write_text(
        json.dumps(cle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def generer_rapport(corpus, resultats, modeles, metriques):
    lignes = [
        "# Comparaison des modèles de La Frontière",
        "",
        "## Objet",
        "",
        "Ce banc compare trois modèles locaux sur le même corpus figé de 61 articles. "
        "Il mesure la conformité automatique et le temps d'exécution. Il ne change "
        "pas le modèle utilisé en production.",
        "",
        "## Corpus et protocole",
        "",
        f"- Commit source : `{corpus['source_commit']}`",
        f"- Empreinte du corpus : `{corpus['sha256_items']}`",
        f"- Nombre d'items : {corpus['nombre_items']}",
        "- Température : 0",
        "- Graine : 20260802",
        "- Deux essais au maximum par résumé et par angle",
        "- Coût API direct : 0 CAD, exécution locale",
        "- Coût énergétique et coût matériel : non mesurés",
        "",
        "## Résultats automatiques",
        "",
        "Les taux par validateur portent sur le premier essai. La non-publication "
        "porte sur l'état final après une reprise au maximum.",
        "",
        "| Modèle | Items | Résumé, phrases | Non latin | Anglais | Angle, phrases | Formule | Non publiables | Reprises | Temps total | Secondes par item |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for modele in modeles:
        m = metriques[modele]
        secondes_item = m["duree_secondes"] / m["items"] if m["items"] else 0
        lignes.append(
            f"| `{modele}` | {m['items']} | {taux(m['resume_nombre_phrases'], m['items'])} "
            f"| {taux(m['caracteres_non_latins'], m['items'])} "
            f"| {taux(m['anglais_residuel'], m['items'])} "
            f"| {taux(m['angle_nombre_phrases'], m['items'])} "
            f"| {taux(m['formule_stereotypee'], m['items'])} "
            f"| {taux(m['non_publiables'], m['items'])} "
            f"| {m['reprises']} | {m['duree_secondes']:.1f} s "
            f"| {secondes_item:.1f} s |"
        )
    lignes.extend([
        "",
        "## Interprétation",
        "",
        "Les validateurs détectent des défauts de forme, pas la profondeur de l'analyse. "
        "Un modèle peut obtenir un faible taux de rejet tout en produisant un texte creux. "
        "La décision exige donc une lecture humaine à l'aveugle de "
        "`evaluation_aveugle.csv`. La clé est conservée séparément dans "
        "`cle_evaluation_aveugle.json`.",
        "",
        "## Décision",
        "",
        "Aucun changement de modèle de production n'est effectué par ce lot. Le choix "
        "revient à l'auteur du site après l'évaluation humaine.",
        "",
    ])
    return "\n".join(lignes)


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--resultats", type=Path, default=RESULTATS_DEFAUT)
    analyseur.add_argument("--corpus", type=Path, default=CORPUS_DEFAUT)
    analyseur.add_argument("--rapport", type=Path, default=RAPPORT_DEFAUT)
    analyseur.add_argument("--evaluation", type=Path, default=EVALUATION_DEFAUT)
    analyseur.add_argument("--cle", type=Path, default=CLE_DEFAUT)
    arguments = analyseur.parse_args()

    resultats = json.loads(arguments.resultats.read_text(encoding="utf-8"))
    corpus = json.loads(arguments.corpus.read_text(encoding="utf-8"))
    modeles = resultats["modeles"]
    metriques = calculer_metriques(resultats, modeles)
    if any(metriques[modele]["items"] != corpus["nombre_items"] for modele in modeles):
        raise RuntimeError("le benchmark est incomplet")

    arguments.rapport.write_text(
        generer_rapport(corpus, resultats, modeles, metriques),
        encoding="utf-8",
    )
    generer_evaluation(corpus, resultats, modeles, arguments.evaluation, arguments.cle)
    print(arguments.rapport)
    print(arguments.evaluation)
    print(arguments.cle)


if __name__ == "__main__":
    main()
