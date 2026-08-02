"""Rejoue la redaction des items deja publies, a partir du corpus fige.

Le correctif du prompt ne nettoie que les items a venir. Les items deja en
ligne gardent la formule stereotypee et les fautes de langue produites par
l'ancien prompt. Le corpus fige de pipeline/benchmark contient les abstracts
d'origine, ce qui permet de les rediger a nouveau sans reinterroger les API
sources et sans toucher a seen.json.

Le modele utilise est celui de la production. Ce script ne choisit pas de
modele : cette decision revient a l'auteur du site.

Par defaut, rien n'est ecrit dans frontiere/data/. Le script produit un
fichier de relecture avant/apres. L'option --appliquer remplace les textes
dans le flux, une fois la relecture faite.

    python -m pipeline.regenerer_flux
    python -m pipeline.regenerer_flux --appliquer
"""

import argparse
import json
import sys
import time
from pathlib import Path

from pipeline import curate

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
FLUX = RACINE / "frontiere" / "data" / "flux.json"
CORPUS = Path(__file__).parent / "benchmark" / "corpus.json"
RELECTURE = Path(__file__).parent / "_regeneration.json"


def charger_corpus():
    contenu = json.loads(CORPUS.read_text(encoding="utf-8"))
    items = contenu["items"] if isinstance(contenu, dict) else contenu
    return {item["id"]: item for item in items}


def generer_en_journalisant(generateur, validateur):
    """Reproduit la politique de reprise unique en gardant trace des essais.

    Meme regle que curate._generer_avec_reprise, mais les essais rejetes sont
    conserves : c'est ce qui permet de mesurer le taux de rejet reel du lot.
    """
    essais = []
    for _ in range(2):
        texte = generateur()
        erreurs = validateur(texte) if texte else ["texte_vide"]
        essais.append({"texte": texte, "erreurs": erreurs})
        if texte and not erreurs:
            return texte, essais
    return None, essais


def rediger(titre, abstract):
    """Retourne (resume, angle, journal des essais)."""
    resume, essais_resume = generer_en_journalisant(
        lambda: curate.resume_ollama(titre, abstract),
        curate.erreurs_resume,
    )
    angle, essais_angle = generer_en_journalisant(
        lambda: curate.angle_eco_ollama(titre, abstract),
        curate.erreurs_angle,
    )
    return resume, angle, {"resume": essais_resume, "angle": essais_angle}


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument(
        "--appliquer",
        action="store_true",
        help="ecrit les textes valides dans frontiere/data/flux.json",
    )
    arguments = analyseur.parse_args()

    if not curate.LLM_ACTIF:
        print(
            "FRONTIERE_LLM=ollama est requis. Rien n'a ete fait.",
            file=sys.stderr,
        )
        return 1

    flux = json.loads(FLUX.read_text(encoding="utf-8"))
    corpus = charger_corpus()
    debut = time.monotonic()

    releve = []
    nb_valides = 0
    for rang, entree in enumerate(flux, start=1):
        source = corpus.get(entree["id"])
        if not source or not source.get("abstract"):
            releve.append({"id": entree["id"], "etat": "abstract_absent"})
            print(f"[{rang}/{len(flux)}] {entree['id']} : abstract absent, ignore")
            continue

        resume, angle, journal = rediger(entree["titre"], source["abstract"])
        valide = bool(resume and angle)
        nb_valides += valide
        releve.append({
            "id": entree["id"],
            "titre": entree["titre"],
            "etat": "valide" if valide else "rejete",
            "avant": {
                "resume_fr": entree.get("resume_fr", ""),
                "angle_eco": entree.get("angle_eco", ""),
            },
            "apres": {"resume_fr": resume or "", "angle_eco": angle or ""},
            "essais": journal,
        })
        print(
            f"[{rang}/{len(flux)}] {entree['id']} : "
            f"{'valide' if valide else 'REJETE'} "
            f"({len(journal['resume'])} essai(s) resume, "
            f"{len(journal['angle'])} essai(s) angle)"
        )

    duree = time.monotonic() - debut
    RELECTURE.write_text(
        json.dumps(
            {
                "modele": curate.OLLAMA_MODEL,
                "duree_secondes": round(duree, 1),
                "items": releve,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"\n{nb_valides}/{len(flux)} items rediges et valides en "
        f"{duree / 60:.1f} min avec {curate.OLLAMA_MODEL}."
    )
    print(f"Relecture avant/apres : {RELECTURE}")

    if not arguments.appliquer:
        print("Rien n'a ete ecrit dans le flux. Relire, puis relancer avec --appliquer.")
        return 0

    par_id = {
        ligne["id"]: ligne
        for ligne in releve
        if ligne.get("etat") == "valide"
    }
    nb_remplaces = 0
    for entree in flux:
        ligne = par_id.get(entree["id"])
        if not ligne:
            continue
        entree["resume_fr"] = ligne["apres"]["resume_fr"]
        entree["angle_eco"] = ligne["apres"]["angle_eco"]
        entree["llm"] = curate.OLLAMA_MODEL
        nb_remplaces += 1

    FLUX.write_text(json.dumps(flux, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{nb_remplaces} items remplaces dans {FLUX}.")
    print("Les items rejetes gardent leur texte precedent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
