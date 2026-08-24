"""Rejoue la redaction des items deja publies, a partir du corpus fige.

Le correctif du prompt ne nettoie que les items a venir. Les items deja en
ligne gardent la formule stereotypee et les fautes de langue produites par
l'ancien prompt. Le corpus fige de pipeline/benchmark contient les abstracts
d'origine, ce qui permet de les rediger a nouveau sans reinterroger les API
sources et sans toucher a seen.json.

Le modele utilise est celui de la production. Ce script ne choisit pas de
modele : cette decision revient a l'auteur du site.

Par defaut, rien n'est ecrit dans frontiere/data/. Le script produit un
fichier de relecture avant/apres, plus un second fichier isolant les seuls
items rediges a l'instant (_regeneration_du_jour.md), utile pour notifier
sans re-signaler chaque jour ce qui est deja en ligne depuis la veille.
L'option --appliquer remplace les textes dans le flux, une fois la
relecture faite ; --depuis-relecture fait de meme sans rien regenerer.

L'option --anglais bascule sur un second usage, distinct du premier : au lieu
de reecrire du francais publie, elle ajoute les champs anglais aux items
publies avant que curate.py sache les rediger. Le francais n'est pas touche.
--estimer chiffre le lot sans appeler le modele.

    python -m pipeline.regenerer_flux
    python -m pipeline.regenerer_flux --appliquer
    python -m pipeline.regenerer_flux --depuis-relecture
    python -m pipeline.regenerer_flux --anglais --estimer
    python -m pipeline.regenerer_flux --anglais --reprendre
    python -m pipeline.regenerer_flux --anglais --depuis-relecture
"""

import argparse
import json
import sys
import time
from pathlib import Path

from pipeline import curate
from pipeline.publish import PAGES_FLUX, generer_jsonld_flux, injecter_jsonld_flux
from pipeline.publish import index_de_page as publish_index_de_page

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
FLUX = RACINE / "frontiere" / "data" / "flux.json"
CORPUS = Path(__file__).parent / "benchmark" / "corpus.json"
RELECTURE = Path(__file__).parent / "_regeneration.json"
RELECTURE_LISIBLE = Path(__file__).parent / "_regeneration.md"
RAPPORT_DU_JOUR = Path(__file__).parent / "_regeneration_du_jour.md"


def _rendre_markdown(titre_document, note, valides, rejetes, modele, duree):
    lignes = [
        f"# {titre_document}",
        "",
        f"Modele : `{modele}`. {len(valides)} items valides, {len(rejetes)} rejetes, "
        f"en {duree / 60:.1f} min.",
        "",
        note,
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

    return "\n".join(lignes)


def ecrire_relecture_lisible(releve, modele, duree):
    """Rend l'avant/apres lisible, le JSON etant fait pour la machine."""
    valides = [ligne for ligne in releve if ligne.get("etat") == "valide"]
    rejetes = [ligne for ligne in releve if ligne.get("etat") == "rejete"]
    texte = _rendre_markdown(
        "Relecture de la redaction rejouee",
        "Les items rejetes gardent leur texte actuel. Ils sont listes en fin de\n"
        "document avec le motif de rejet.",
        valides,
        rejetes,
        modele,
        duree,
    )
    RELECTURE_LISIBLE.write_text(texte, encoding="utf-8")


def ecrire_rapport_du_jour(releve, modele, duree):
    """Isole ce qui vient d'etre publie aujourd'hui, pour une relecture a posteriori.

    releve accumule les items reconduits depuis le cache (nouveau=False) et
    ceux traites a l'instant (nouveau=True). Seuls ces derniers viennent
    d'atteindre le site : c'est le seul sous-ensemble qu'une notification
    quotidienne doit signaler, sous peine de re-notifier chaque jour les
    memes items deja lus et deja en ligne.
    """
    du_jour = [ligne for ligne in releve if ligne.get("nouveau")]
    valides = [ligne for ligne in du_jour if ligne.get("etat") == "valide"]
    rejetes = [ligne for ligne in du_jour if ligne.get("etat") == "rejete"]
    if not valides and not rejetes:
        RAPPORT_DU_JOUR.unlink(missing_ok=True)
        return
    texte = _rendre_markdown(
        "Textes publies aujourd'hui sur La Frontiere",
        "Ces textes sont deja en ligne. Cette relecture est a posteriori : "
        "toute correction se fait en editant frontiere/data/flux.json.",
        valides,
        rejetes,
        modele,
        duree,
    )
    RAPPORT_DU_JOUR.write_text(texte, encoding="utf-8")


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
    source = f"{titre} {abstract}"
    resume, essais_resume = generer_en_journalisant(
        lambda: curate.resume_ollama(titre, abstract),
        lambda texte: curate.erreurs_resume(texte) + curate.erreurs_invention(texte, source),
    )
    angle, essais_angle = generer_en_journalisant(
        lambda: curate.angle_eco_ollama(titre, abstract),
        lambda texte: curate.erreurs_angle(texte) + curate.erreurs_invention(texte, source),
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
    # Sans cette ligne, frontiere/index.html continuerait d'indexer les
    # anciens resume_fr/angle_eco jusqu'a la prochaine execution de
    # publish.py : le JSON-LD servi aux moteurs divergerait de flux.json,
    # donc de ce que la page affiche reellement.
    for langue in PAGES_FLUX:
        injecter_jsonld_flux(
            generer_jsonld_flux(flux, langue), publish_index_de_page(langue)
        )
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


# --- Rattrapage des champs anglais des items deja publies ---------------
#
# Le mode ci-dessus reecrit du francais deja en ligne : chaque item a un
# avant et un apres, et la relecture sert a les comparer. Le rattrapage
# anglais n'a pas d'avant. Il ajoute resume_en et angle_eco_en aux items
# publies avant que curate.py sache les rediger, et ne touche jamais au
# francais. D'ou un mode distinct, avec ses propres fichiers de relecture :
# les melanger obligerait a accepter une reecriture francaise pour obtenir
# un champ anglais.

RATTRAPAGE_EN = Path(__file__).parent / "_rattrapage_en.json"
RATTRAPAGE_EN_LISIBLE = Path(__file__).parent / "_rattrapage_en.md"
CANDIDATS_BRUTS = Path(__file__).parent / "_candidats_bruts.json"

# Tarifs du repli, releves le 24 juin 2026 : claude-haiku-4-5, 1 $ US par
# million de tokens en entree et 5 $ en sortie. Le fournisseur principal
# tourne sur un palier gratuit compte en requetes par jour, pas en tokens :
# son cout se lit en jours de quota, jamais en dollars.
PRIX_ENTREE_PAR_MTOKEN = 1.0
PRIX_SORTIE_PAR_MTOKEN = 5.0
# Approximation usuelle pour de l'anglais academique. Elle donne un ordre de
# grandeur avant de lancer, elle ne facture rien.
CARACTERES_PAR_TOKEN = 4
# Le prompt reprend au plus 1500 caracteres d'abstract
# (curate.construire_prompt_resume_en) et environ 600 de consignes. Deux
# phrases en sortie tiennent dans 400 caracteres.
ABSTRACT_MAX_DANS_PROMPT = 1500
CARACTERES_CONSIGNES = 600
CARACTERES_SORTIE = 400


def charger_abstracts():
    """Abstracts disponibles localement, la collecte recente d'abord.

    Deux sources, aucune complete. Le corpus de benchmark couvre les items
    figes au moment de sa reconstruction; ceux collectes depuis n'y sont pas.
    _candidats_bruts.json rattrape une partie du reste, mais il est ecrase a
    chaque collecte et ne garde donc que le dernier lot.

    Rien n'est retelecharge ici. Un abstract recupere aujourd'hui ne serait
    pas forcement celui qui a servi a rediger le francais publie, et l'ecart
    entre les deux langues d'un meme item deviendrait invisible.
    """
    abstracts = {}
    for fichier in (CORPUS, CANDIDATS_BRUTS):
        if not fichier.exists():
            continue
        contenu = json.loads(fichier.read_text(encoding="utf-8"))
        items = contenu["items"] if isinstance(contenu, dict) else contenu
        for item in items:
            if item.get("abstract") and item["id"] not in abstracts:
                abstracts[item["id"]] = item["abstract"]
    return abstracts


def trier_pour_rattrapage(flux, abstracts):
    """Repartit le flux en (a rediger, deja complets, sans abstract)."""
    a_rediger, complets, sans_abstract = [], [], []
    for entree in flux:
        if entree.get("resume_en") and entree.get("angle_eco_en"):
            complets.append(entree)
        elif abstracts.get(entree["id"]):
            a_rediger.append(entree)
        else:
            sans_abstract.append(entree)
    return a_rediger, complets, sans_abstract


def estimer_cout(a_rediger, abstracts):
    """Cout d'un rattrapage complet, en appels, en tokens et en dollars.

    Deux champs par item, un essai chacun au mieux, deux au pire quand le
    validateur rejette et relance. C'est la borne haute qui compte : un
    abstract long produit plus souvent un texte hors format.
    """
    appels_min = 2 * len(a_rediger)
    appels_max = 4 * len(a_rediger)
    caracteres_par_appel = sum(
        min(len(abstracts[entree["id"]]), ABSTRACT_MAX_DANS_PROMPT)
        + CARACTERES_CONSIGNES
        for entree in a_rediger
    )
    # Deux champs, deux essais : le meme prompt part quatre fois par item.
    tokens_entree_max = 4 * caracteres_par_appel / CARACTERES_PAR_TOKEN
    tokens_sortie_max = appels_max * CARACTERES_SORTIE / CARACTERES_PAR_TOKEN
    dollars_max = (
        tokens_entree_max / 1e6 * PRIX_ENTREE_PAR_MTOKEN
        + tokens_sortie_max / 1e6 * PRIX_SORTIE_PAR_MTOKEN
    )
    return {
        "items": len(a_rediger),
        "appels_min": appels_min,
        "appels_max": appels_max,
        "tokens_entree_max": int(tokens_entree_max),
        "tokens_sortie_max": int(tokens_sortie_max),
        "dollars_repli_max": round(dollars_max, 2),
    }


def afficher_estimation(flux, abstracts):
    """Chiffre le rattrapage sans appeler le modele."""
    a_rediger, complets, sans_abstract = trier_pour_rattrapage(flux, abstracts)
    estimation = estimer_cout(a_rediger, abstracts)

    print(f"Flux : {len(flux)} items publies.")
    print(f"  deja bilingues : {len(complets)}")
    print(f"  a rattraper : {estimation['items']}")
    print(f"  sans abstract local, hors de portee : {len(sans_abstract)}")
    print()
    print(
        f"Appels au modele : {estimation['appels_min']} au mieux, "
        f"{estimation['appels_max']} au pire (2 champs, 1 ou 2 essais)."
    )
    print(
        f"Tokens au pire : {estimation['tokens_entree_max']} en entree, "
        f"{estimation['tokens_sortie_max']} en sortie."
    )
    print(
        "Cout au pire si tout passe par le repli claude-haiku-4-5 : "
        f"{estimation['dollars_repli_max']} $ US."
    )
    if curate.BUDGET_APPELS:
        par_lot = curate.BUDGET_APPELS // curate.APPELS_MAX_ANGLAIS_SEUL
        lots = -(-estimation["items"] // par_lot) if par_lot else 0
        print(
            f"Avec LLM_BUDGET_APPELS={curate.BUDGET_APPELS}, soit {par_lot} "
            f"items par execution : {lots} executions au pire."
        )
    else:
        print(
            "LLM_BUDGET_APPELS n'est pas defini : le lot ira jusqu'au bout en "
            "une fois, quitte a heurter le quota du fournisseur."
        )
    if sans_abstract:
        print()
        print(
            f"Les {len(sans_abstract)} items sans abstract local gardent leur "
            "seul francais, et la page anglaise sert ce francais en repli. "
            "Les rattraper demanderait de retelecharger leur abstract."
        )
    return a_rediger, sans_abstract


def rediger_anglais(titre, abstract):
    """Retourne (resume_en, angle_en, journal des essais)."""
    resume, essais_resume = generer_en_journalisant(
        lambda: curate.resume_en_ollama(titre, abstract),
        lambda texte: curate.erreurs_resume_en(texte)
        + curate.erreurs_invention(texte, abstract),
    )
    angle, essais_angle = generer_en_journalisant(
        lambda: curate.angle_eco_en_ollama(titre, abstract),
        lambda texte: curate.erreurs_angle_en(texte)
        + curate.erreurs_invention(texte, abstract),
    )
    return resume, angle, {"resume_en": essais_resume, "angle_en": essais_angle}


def ecrire_rattrapage_lisible(releve, modele, duree):
    valides = [ligne for ligne in releve if ligne.get("etat") == "valide"]
    rejetes = [ligne for ligne in releve if ligne.get("etat") == "rejete"]
    lignes = [
        "# Rattrapage anglais de La Frontiere",
        "",
        f"Modele : `{modele}`. {len(valides)} items rediges, "
        f"{len(rejetes)} rejetes, en {duree / 60:.1f} min.",
        "",
        "Le francais publie n'est pas touche. Un item rejete garde son "
        "absence de champs anglais, et la page /en/ sert son texte francais.",
        "",
    ]
    for ligne in valides:
        lignes += [
            f"## {ligne['titre']}",
            "",
            "**Summary**  ",
            ligne["apres"]["resume_en"],
            "",
            "**Angle**  ",
            ligne["apres"]["angle_eco_en"],
            "",
        ]
    if rejetes:
        lignes += ["## Rejetes", ""]
        lignes += [f"- {ligne['titre']}" for ligne in rejetes]
        lignes += [""]
    RATTRAPAGE_EN_LISIBLE.write_text("\n".join(lignes), encoding="utf-8")


def ecrire_flux_anglais(flux, releve):
    """Ajoute les champs anglais valides, sans rien ecraser.

    Un item qui a recu ses champs anglais entre-temps, par une execution
    normale du pipeline, n'est pas retouche : son texte a ete redige depuis
    l'abstract courant et vaut mieux que celui d'un lot de rattrapage.
    """
    par_id = {
        ligne["id"]: ligne for ligne in releve if ligne.get("etat") == "valide"
    }
    nb_completes = 0
    ignores = []
    for entree in flux:
        ligne = par_id.get(entree["id"])
        if not ligne:
            continue
        if entree.get("resume_en") or entree.get("angle_eco_en"):
            ignores.append(entree["titre"])
            continue
        entree["resume_en"] = ligne["apres"]["resume_en"]
        entree["angle_eco_en"] = ligne["apres"]["angle_eco_en"]
        nb_completes += 1

    FLUX.write_text(json.dumps(flux, ensure_ascii=False, indent=2), encoding="utf-8")
    # Le JSON-LD ne porte que le francais (inLanguage "fr") : cet appel est
    # sans effet visible tant que les champs anglais n'y entrent pas. Le
    # rendre inconditionnel ne coute rien et garde ecrire_flux et
    # ecrire_flux_anglais idempotents l'un vis-a-vis de l'autre.
    for langue in PAGES_FLUX:
        injecter_jsonld_flux(
            generer_jsonld_flux(flux, langue), publish_index_de_page(langue)
        )
    print(f"{nb_completes} items completes en anglais dans {FLUX}.")
    for titre in ignores:
        print(f"Ignore, deja bilingue depuis la relecture : {titre}")
    return nb_completes


def appliquer_rattrapage():
    """Applique un rattrapage deja produit, sans rien rediger."""
    if not RATTRAPAGE_EN.exists():
        print(
            f"{RATTRAPAGE_EN} est absent. Lancer d'abord le rattrapage.",
            file=sys.stderr,
        )
        return 1
    relecture = json.loads(RATTRAPAGE_EN.read_text(encoding="utf-8"))
    flux = json.loads(FLUX.read_text(encoding="utf-8"))
    print(f"Application du rattrapage produit avec {relecture['modele']}.")
    ecrire_flux_anglais(flux, relecture["items"])
    return 0


def mode_anglais(arguments):
    """Rattrape resume_en et angle_eco_en sur les items deja publies."""
    flux = json.loads(FLUX.read_text(encoding="utf-8"))

    if arguments.depuis_relecture:
        return appliquer_rattrapage()

    abstracts = charger_abstracts()

    if arguments.estimer:
        afficher_estimation(flux, abstracts)
        print()
        print("Estimation seule : aucun appel n'a ete fait.")
        return 0

    if not curate.LLM_ACTIF:
        print(
            "FRONTIERE_LLM doit valoir ollama ou api. Rien n'a ete fait.",
            file=sys.stderr,
        )
        return 1

    a_rediger, _ = afficher_estimation(flux, abstracts)
    print()

    deja_faits = {}
    if arguments.reprendre and RATTRAPAGE_EN.exists():
        precedent = json.loads(RATTRAPAGE_EN.read_text(encoding="utf-8"))
        deja_faits = {
            ligne["id"]: ligne
            for ligne in precedent.get("items", [])
            if ligne.get("etat") in ("valide", "rejete")
        }
        print(f"Reprise : {len(deja_faits)} items deja traites seront conserves.")

    debut = time.monotonic()
    releve = []
    interrompu = None
    budget_atteint = False
    for rang, entree in enumerate(a_rediger, start=1):
        if entree["id"] in deja_faits:
            releve.append(dict(deja_faits[entree["id"]], nouveau=False))
            print(f"[{rang}/{len(a_rediger)}] {entree['id']} : conserve")
            continue

        if curate.budget_epuise(curate.APPELS_MAX_ANGLAIS_SEUL):
            budget_atteint = True
            print(
                f"[{rang}/{len(a_rediger)}] budget d'appels atteint, "
                "le reste attend la prochaine execution"
            )
            break

        try:
            resume, angle, journal = rediger_anglais(
                entree["titre"], abstracts[entree["id"]]
            )
        except curate.OllamaIndisponible as erreur:
            interrompu = erreur
            print(
                f"[{rang}/{len(a_rediger)}] interruption : {erreur}",
                file=sys.stderr,
            )
            break

        valide = bool(resume and angle)
        releve.append({
            "id": entree["id"],
            "titre": entree["titre"],
            "etat": "valide" if valide else "rejete",
            "nouveau": True,
            "apres": {"resume_en": resume or "", "angle_eco_en": angle or ""},
            "essais": journal,
        })
        print(
            f"[{rang}/{len(a_rediger)}] {entree['id']} : "
            f"{'valide' if valide else 'REJETE'}"
        )

    duree = time.monotonic() - debut
    RATTRAPAGE_EN.write_text(
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
    ecrire_rattrapage_lisible(releve, curate.modele_actif(), duree)

    nb_valides = sum(1 for ligne in releve if ligne.get("etat") == "valide")
    print(
        f"\n{nb_valides} items rediges en anglais en {duree / 60:.1f} min "
        f"avec {curate.modele_actif()}."
    )
    print(f"Relecture : {RATTRAPAGE_EN_LISIBLE}")

    if interrompu:
        print(
            "\nLot interrompu. Relancer avec --anglais --reprendre pour "
            "continuer sans refaire le debut.",
            file=sys.stderr,
        )
        return 2

    if budget_atteint:
        # Meme raison que dans le mode francais : arret prevu, pas panne. Un
        # code de sortie non nul ferait passer l'execution au rouge alors que
        # tout s'est deroule comme prevu.
        print("\nLot du jour termine dans la limite du budget.")
        return 0

    if not arguments.appliquer:
        print("Rien n'a ete ecrit. Relire, puis relancer avec --depuis-relecture.")
        return 0

    ecrire_flux_anglais(flux, releve)
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
        "--anglais",
        action="store_true",
        help=(
            "rattrape resume_en et angle_eco_en sur les items deja publies, "
            "sans toucher au francais. A combiner avec --estimer, "
            "--reprendre, --appliquer ou --depuis-relecture."
        ),
    )
    analyseur.add_argument(
        "--estimer",
        action="store_true",
        help=(
            "avec --anglais : compte les items a rattraper et le cout en "
            "appels, en tokens et en dollars, sans appeler le modele."
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

    if arguments.anglais:
        return mode_anglais(arguments)

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
    budget_atteint = False
    for rang, entree in enumerate(flux, start=1):
        if entree["id"] in deja_faits:
            ligne = dict(deja_faits[entree["id"]], nouveau=False)
            releve.append(ligne)
            nb_valides += ligne["etat"] == "valide"
            print(f"[{rang}/{len(flux)}] {entree['id']} : conserve ({ligne['etat']})")
            continue

        source = corpus.get(entree["id"])
        if not source or not source.get("abstract"):
            releve.append({"id": entree["id"], "etat": "abstract_absent"})
            print(f"[{rang}/{len(flux)}] {entree['id']} : abstract absent, ignore")
            continue

        if curate.budget_epuise():
            # S'arreter avant le mur plutot que dessus. Un quota atteint se
            # paie en requetes perdues : le service refuse, le code retente,
            # et chaque tentative consomme une unite du quota du lendemain.
            budget_atteint = True
            print(
                f"[{rang}/{len(flux)}] budget d'appels atteint, "
                "le reste attend la prochaine execution"
            )
            break

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
            "nouveau": True,
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
    ecrire_rapport_du_jour(releve, curate.modele_actif(), duree)

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

    if budget_atteint:
        # Arret prevu, pas panne : le lot du jour est complet. Le code de
        # sortie doit rester 0, sinon l'execution planifiee passe au rouge
        # chaque jour alors que tout se deroule comme prevu.
        restants = len(flux) - len([l for l in releve if l.get("etat")])
        print(
            f"\nLot du jour termine dans la limite du budget. "
            f"{restants} items attendent la prochaine execution."
        )
        return 0

    if not arguments.appliquer:
        print("Rien n'a ete ecrit dans le flux. Relire, puis relancer avec --appliquer.")
        return 0

    ecrire_flux(flux, releve, curate.modele_actif())
    return 0


if __name__ == "__main__":
    sys.exit(main())
