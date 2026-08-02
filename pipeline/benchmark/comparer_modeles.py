"""Compare plusieurs modèles Ollama sur le corpus figé de La Frontière."""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from pipeline.curate import (
    construire_prompt_angle,
    construire_prompt_resume,
    erreurs_angle,
    erreurs_resume,
)


MODELES_DEFAUT = ["qwen2.5:3b", "qwen2.5:7b", "llama3.2:3b"]
CORPUS_DEFAUT = Path(__file__).with_name("corpus.json")
RESULTATS_DEFAUT = Path(__file__).with_name("resultats.json")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")


def normaliser_sortie(texte):
    return (texte or "").strip().replace("\u2014", ",")


def appeler_ollama(modele, prompt, timeout):
    debut = time.perf_counter()
    reponse = requests.post(
        OLLAMA_URL,
        json={
            "model": modele,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "seed": 20260802},
        },
        timeout=timeout,
    )
    duree = time.perf_counter() - debut
    reponse.raise_for_status()
    donnees = reponse.json()
    return normaliser_sortie(donnees.get("response", "")), duree, donnees


def evaluer_champ(modele, prompt, validateur, timeout):
    essais = []
    for numero in (1, 2):
        try:
            texte, duree, metadonnees = appeler_ollama(modele, prompt, timeout)
            erreurs = validateur(texte)
            essais.append({
                "essai": numero,
                "texte": texte,
                "erreurs": erreurs,
                "duree_secondes": round(duree, 3),
                "eval_count": metadonnees.get("eval_count"),
                "prompt_eval_count": metadonnees.get("prompt_eval_count"),
            })
            if not erreurs:
                return {"valide": True, "essais": essais, "texte_final": texte}
        except Exception as erreur:
            essais.append({
                "essai": numero,
                "texte": "",
                "erreurs": ["appel_ollama"],
                "duree_secondes": 0.0,
                "erreur": str(erreur),
            })
    return {"valide": False, "essais": essais, "texte_final": ""}


def charger_ou_initialiser(corpus, modeles, sortie):
    if sortie.exists():
        resultat = json.loads(sortie.read_text(encoding="utf-8"))
        if resultat.get("corpus_sha256") != corpus["sha256_items"]:
            raise RuntimeError("le fichier de reprise ne correspond pas au corpus")
        return resultat
    return {
        "schema_version": 1,
        "corpus_sha256": corpus["sha256_items"],
        "modeles": modeles,
        "cout_api_direct_cad": 0,
        "cout_energie": "non mesure",
        "demarre_le": datetime.now(timezone.utc).isoformat(),
        "items": {},
    }


def sauvegarder(resultats, sortie):
    sortie.write_text(
        json.dumps(resultats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verifier_modeles(modeles):
    reponse = requests.get(OLLAMA_URL.rsplit("/", 1)[0] + "/tags", timeout=15)
    reponse.raise_for_status()
    installes = {modele["name"] for modele in reponse.json().get("models", [])}
    manquants = [modele for modele in modeles if modele not in installes]
    if manquants:
        raise RuntimeError(f"modeles Ollama absents : {', '.join(manquants)}")


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--corpus", type=Path, default=CORPUS_DEFAUT)
    analyseur.add_argument("--sortie", type=Path, default=RESULTATS_DEFAUT)
    analyseur.add_argument("--modeles", nargs="+", default=MODELES_DEFAUT)
    analyseur.add_argument("--limite", type=int)
    analyseur.add_argument("--timeout", type=int, default=180)
    arguments = analyseur.parse_args()

    corpus = json.loads(arguments.corpus.read_text(encoding="utf-8"))
    verifier_modeles(arguments.modeles)
    resultats = charger_ou_initialiser(corpus, arguments.modeles, arguments.sortie)
    items = corpus["items"][:arguments.limite] if arguments.limite else corpus["items"]
    total = len(items) * len(arguments.modeles)
    termines = sum(len(modeles) for modeles in resultats["items"].values())

    for modele in arguments.modeles:
        for item in items:
            resultats["items"].setdefault(item["id"], {})
            if modele in resultats["items"][item["id"]]:
                continue
            resume = evaluer_champ(
                modele,
                construire_prompt_resume(item["titre"], item["abstract"]),
                erreurs_resume,
                arguments.timeout,
            )
            angle = evaluer_champ(
                modele,
                construire_prompt_angle(item["titre"], item["abstract"]),
                erreurs_angle,
                arguments.timeout,
            )
            resultats["items"][item["id"]][modele] = {
                "titre": item["titre"],
                "resume": resume,
                "angle": angle,
                "publiable": resume["valide"] and angle["valide"],
            }
            termines += 1
            sauvegarder(resultats, arguments.sortie)
            print(
                f"[{termines}/{total}] {modele} | {item['id']} | "
                f"publiable={resume['valide'] and angle['valide']}",
                flush=True,
            )

    resultats["termine_le"] = datetime.now(timezone.utc).isoformat()
    sauvegarder(resultats, arguments.sortie)
    print(f"Résultats écrits dans {arguments.sortie}")


if __name__ == "__main__":
    main()
