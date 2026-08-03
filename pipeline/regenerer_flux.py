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
RELECTURE_LISIBLE = Path(__file__).parent / "_regeneration.md"


def ecrire_relecture_lisible(releve, modele, duree):
    """Rend l'avant/apres lisible, le JSON etant fait pour la machine."""
    valides = [ligne for ligne in releve if ligne.get("etat") == "valide"]
    rejetes = [ligne for ligne in releve if ligne.get("etat") == "rejete"]

    lignes = [
        "# Relecture de la redaction rejouee",
        "",
        f"Modele : `{modele}`. {len(valides)} items valides, {len(rejetes)} rejetes, "
        f"en {duree / 60:.1f} min.",
        "",
        "Les items rejetes gardent leur texte actuel. Ils sont listes en fin de",
        "document avec le motif de rejet.",
        "",
    ]

    for ligne in valides:
        lignes += [
            f"## {ligne['titre']}",
            "",
            "**Angle, avant**  ",
            ligne["avant"]["angle_eco"] or "_vide_",
            "",
            "**Angle, apres**  ",
            ligne["apres"]["angle_eco"],
            "",
            "**Resume, avant**  ",
            ligne["avant"]["resume_fr"] or "_vide_",
            "",
            "**Resume, apres**  ",
            ligne["apres"]["resume_fr"],
            "",
        ]

    if rejetes:
        lignes += ["## Items rejetes", ""]
        for ligne in rejetes:
            motifs = sorted({
                erreur
                for essais in ligne["essais"].values()
                for essai in essais
                for erreur in essai["erreurs"]
            })
            lignes.append(f"- **{ligne['titre']}** : {', '.join(motifs)}")
        lignes.append("")

    RELECTURE_LISIBLE.write_text("\n".join(lignes), encoding="utf-8")


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


def ecrire_flux(flux, releve, modele):
    """Remplace les textes des items valides et ecrit le flux.

    Un item dont le texte courant ne correspond plus a celui qui figurait
    dans la relecture n'est pas touche : entre la relecture et l'application,
    le bot ou une correction manuelle a pu le modifier, et l'ecraser
    reviendrait a annuler ce changement sans le dire.
    """
    par_id = {ligne["id"]: ligne for ligne in releve if ligne.get("etat") == "valide"}
    nb_remplaces = 0
    ignores = []
    for entree in flux:
        ligne = par_id.get(entree["id"])
        if not ligne:
            continue
        if entree.get("angle_eco", "") != ligne["avant"]["angle_eco"]:
            ignores.append(entree["titre"])
            continue
        entree["resume_fr"] = ligne["apres"]["resume_fr"]
        entree["angle_eco"] = ligne["apres"]["angle_eco"]
        entree["llm"] = modele
        nb_remplaces += 1

    FLUX.write_text(json.dumps(flux, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{nb_remplaces} items remplaces dans {FLUX}.")
    print("Les items rejetes gardent leur texte precedent.")
    for titre in ignores:
        print(f"Ignore, modifie depuis la relecture : {titre}")
    return nb_remplaces


def appliquer_relecture():
    """Applique une relecture deja produite, sans rien regenerer."""
    if not RELECTURE.exists():
        print(
            f"{RELECTURE} est absent. Lancer d'abord la regeneration.",
            file=sys.stderr,
        )
        return 1
    relecture = json.loads(RELECTURE.read_text(encoding="utf-8"))
    flux = json.loads(FLUX.read_text(encoding="utf-8"))
    print(f"Application de la relecture produite avec {relecture['modele']}.")
    ecrire_flux(flux, relecture["items"], relecture["modele"])
    return 0


def main():
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument(
        "--appliquer",
        action="store_true",
        help="ecrit les textes valides dans frontiere/data/flux.json",
    )
    analyseur.add_argument(
        "--reprendre",
        action="store_true",
        help=(
            "conserve les items deja rediges dans _regeneration.json et ne "
            "traite que les autres. Utile quand un quota journalier a "
            "interrompu un passage precedent."
        ),
    )
    analyseur.add_argument(
        "--depuis-relecture",
        action="store_true",
        help=(
            "applique le contenu de _regeneration.json sans rien regenerer. "
            "C'est ce qui garantit que le texte publie est celui qui a ete relu, "
            "le modele ne produisant pas deux fois la meme sortie."
        ),
    )
    arguments = analyseur.parse_args()

    if arguments.depuis_relecture:
        return appliquer_relecture()

    if not curate.LLM_ACTIF:
        print(
            "FRONTIERE_LLM doit valoir ollama ou api. Rien n'a ete fait.",
            file=sys.stderr,
        )
        return 1

    flux = json.loads(FLUX.read_text(encoding="utf-8"))
    corpus = charger_corpus()
    debut = time.monotonic()

    releve = []
    deja_faits = {}
    if arguments.reprendre and RELECTURE.exists():
        precedent = json.loads(RELECTURE.read_text(encoding="utf-8"))
        deja_faits = {
            ligne["id"]: ligne
            for ligne in precedent.get("items", [])
            if ligne.get("etat") in ("valide", "rejete")
        }
        print(f"Reprise : {len(deja_faits)} items deja rediges seront conserves.")

    nb_valides = 0
    interrompu = None
    for rang, entree in enumerate(flux, start=1):
        if entree["id"] in deja_faits:
            ligne = deja_faits[entree["id"]]
            releve.append(ligne)
            nb_valides += ligne["etat"] == "valide"
            print(f"[{rang}/{len(flux)}] {entree['id']} : conserve ({ligne['etat']})")
            continue

        source = corpus.get(entree["id"])
        if not source or not source.get("abstract"):
            releve.append({"id": entree["id"], "etat": "abstract_absent"})
            print(f"[{rang}/{len(flux)}] {entree['id']} : abstract absent, ignore")
            continue

        try:
            resume, angle, journal = rediger(entree["titre"], source["abstract"])
        except curate.OllamaIndisponible as erreur:
            # Quota journalier ou panne : on garde ce qui est deja redige plutot
            # que de tout perdre. --reprendre repart d'ici au prochain passage.
            interrompu = erreur
            print(
                f"[{rang}/{len(flux)}] interruption : {erreur}",
                file=sys.stderr,
            )
            break

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
                "modele": curate.modele_actif(),
                "duree_secondes": round(duree, 1),
                "items": releve,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    ecrire_relecture_lisible(releve, curate.modele_actif(), duree)

    print(
        f"\n{nb_valides}/{len(flux)} items rediges et valides en "
        f"{duree / 60:.1f} min avec {curate.modele_actif()}."
    )
    print(f"Relecture avant/apres : {RELECTURE_LISIBLE}")
    print(f"Detail des essais : {RELECTURE}")

    if interrompu:
        print(
            f"\nLot interrompu apres {len(releve)} items sur {len(flux)}. "
            "Relancer avec --reprendre pour continuer sans refaire le debut.",
            file=sys.stderr,
        )
        return 2

    if not arguments.appliquer:
        print("Rien n'a ete ecrit dans le flux. Relire, puis relancer avec --appliquer.")
        return 0

    ecrire_flux(flux, releve, curate.modele_actif())
    return 0


if __name__ == "__main__":
    sys.exit(main())
