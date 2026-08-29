"""Redige le plan d'un carrousel LinkedIn quand la veille designe un signal.

La Frontiere publie plusieurs fois par semaine, mais rien de cette veille ne
sortait du site. Ce module transforme une execution qui a designe un signal
en brouillon de carrousel : la matiere factuelle est deja mise en page, et
seul le jugement editorial reste a ecrire.

Le brouillon n'est jamais un livrable fini. Trois emplacements marques
[A COMPLETER] attendent l'angle d'Ulrich : la these qui relie les papiers,
ce que le lecteur doit en retenir, et la question de cloture. Un carrousel
qui resume des resumes n'a aucune valeur de marque, puisque n'importe qui
peut lire les memes abstracts. Le script fait la mise en forme, pas l'avis.

Deux precautions tiennent a l'origine des textes. Les resumes du flux sont
rediges par un modele de langage : le brouillon rappelle lequel a tourne et
demande une verification a la source avant publication sous le nom d'Ulrich.
Et une liste de mots sensibles signale les sujets qui pourraient etre
rapportes a son employeur, sans bloquer la generation : c'est un
avertissement pour la relecture, pas une censure automatique.

Ne produit rien quand l'execution n'a publie aucun item portant le signal,
pour que le workflow saute l'ouverture de l'issue au lieu d'en creer une
vide. Une mise a jour de routine ne merite pas une demande de validation.

Ecrit deux fichiers : le plan durable dans carrousels/, verse au depot, et
une copie transitoire qui devient le corps de l'issue de validation.

    python -m pipeline.rendre_carrousel
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
FLUX = RACINE / "frontiere" / "data" / "flux.json"
META = RACINE / "frontiere" / "data" / "meta.json"
CURES = Path(__file__).parent / "_candidats_cures.json"
DOSSIER = RACINE / "carrousels"
SORTIE = Path(__file__).parent / "_carrousel_du_jour.md"
SORTIE_TITRE = Path(__file__).parent / "_carrousel_du_jour_titre.txt"
PAGE = "https://djidonou.com/frontiere/"
LONGUEUR_TITRE = 120

A_COMPLETER = "[A COMPLETER]"

# Sujets sur lesquels une publication personnelle pourrait etre rapportee au
# Commissaire au bien-etre et aux droits des enfants. La liste ne bloque
# rien : elle ajoute un avertissement en tete du brouillon pour que la
# relecture soit faite en connaissance de cause, plutot que de decouvrir le
# probleme apres la mise en ligne.
MOTS_SENSIBLES = (
    "enfance",
    "enfant",
    "jeunesse",
    "protection de la jeunesse",
    "bien-etre",
    "bien-être",
    "commissaire",
    "quebec",
    "québec",
    "dpj",
    "child",
    "children",
    "youth",
    "well-being",
    "wellbeing",
)


def charger(fichier, defaut):
    if not fichier.exists():
        return defaut
    contenu = json.loads(fichier.read_text(encoding="utf-8"))
    return contenu["items"] if isinstance(contenu, dict) else contenu


def items_publies(cures, flux):
    """Candidats rediges qui se retrouvent bien dans le flux publie."""
    par_id = {entree["id"]: entree for entree in flux}
    return [par_id[candidat["id"]] for candidat in cures if candidat["id"] in par_id]


def separer_signal(items):
    """Rend (signal, autres). Le signal est l'item porteur, s'il y en a un."""
    signal = next((item for item in items if item.get("signal")), None)
    autres = [item for item in items if item is not signal]
    return signal, autres


def mots_sensibles_reperes(items):
    """Mots de la liste de vigilance presents dans les textes publies."""
    champs = ("titre", "resume_fr", "angle_eco", "source")
    corpus = " ".join(
        str(item.get(champ, "")) for item in items for champ in champs
    ).lower()
    return sorted({mot for mot in MOTS_SENSIBLES if mot in corpus})


def modeles_utilises(items):
    """Modeles de langage ayant redige les textes du lot."""
    return sorted({item["llm"] for item in items if item.get("llm")})


def reference(item):
    """Ligne source, auteurs et date pour une diapositive."""
    morceaux = [item.get("auteurs", ""), item.get("source", ""), item.get("date_publication", "")]
    return ", ".join(morceau for morceau in morceaux if morceau)


def rendre_titre(date):
    return f"Carrousel La Frontiere a valider : {date}"[:LONGUEUR_TITRE]


def diapositive_item(numero, item, role):
    lignes = [f"## Diapositive {numero}, {role}", ""]
    lignes.append(f"**{item.get('titre', '')}**")
    lignes.append(reference(item))
    lignes.append("")
    resume = str(item.get("resume_fr", "")).strip()
    if resume:
        lignes.append(resume)
        lignes.append("")
    angle = str(item.get("angle_eco", "")).strip()
    if angle:
        lignes.append(f"Enjeu economique retenu par la veille : {angle}")
        lignes.append("")
    lignes.append(f"Source : {item.get('url', '')}")
    lignes.append("")
    lignes.append("---")
    lignes.append("")
    return lignes


def rendre(items, date, nb_flux):
    signal, autres = separer_signal(items)
    lignes = [f"# Carrousel La Frontiere, {date}", ""]
    lignes.append("Statut : PLAN A VALIDER. Aucune conversion en PDF avant accord.")
    lignes.append("")

    sensibles = mots_sensibles_reperes(items)
    if sensibles:
        lignes.append(
            "VIGILANCE : le lot touche des termes qui pourraient etre rapportes "
            "a ton employeur (" + ", ".join(sensibles) + "). Relis l'angle avant "
            "de publier, ou retire l'item concerne du carrousel."
        )
        lignes.append("")

    lignes.append("---")
    lignes.append("")

    lignes.append("## Diapositive 1, couverture")
    lignes.append("")
    lignes.append(f"**{A_COMPLETER} : l'accroche qui relie les papiers de la semaine.**")
    lignes.append("")
    lignes.append(f"La Frontiere, veille du {date}")
    lignes.append("")
    lignes.append("---")
    lignes.append("")

    numero = 2
    if signal:
        lignes += diapositive_item(numero, signal, "le signal de la semaine")
        numero += 1
        lignes.append(f"## Diapositive {numero}, pourquoi ca compte")
        lignes.append("")
        lignes.append(
            f"{A_COMPLETER} : ton angle d'economiste sur le signal. Ce que le "
            "resultat change pour la theorie, la mesure ou la decision publique. "
            "C'est la diapositive qui te distingue d'un agregateur."
        )
        lignes.append("")
        lignes.append("---")
        lignes.append("")
        numero += 1

    for item in autres:
        lignes += diapositive_item(numero, item, "aussi dans la veille")
        numero += 1

    if signal and autres:
        lignes.append(f"## Diapositive {numero}, le fil commun")
        lignes.append("")
        lignes.append(
            f"{A_COMPLETER} : la these qui tient le carrousel ensemble, ou le "
            "constat que ces travaux ne se rejoignent pas et pourquoi c'est "
            "interessant."
        )
        lignes.append("")
        lignes.append("---")
        lignes.append("")
        numero += 1

    lignes.append(f"## Diapositive {numero}, d'ou vient cette veille")
    lignes.append("")
    lignes.append(
        "La Frontiere suit l'intersection entre economie et intelligence "
        "artificielle. Collecte automatisee, filtrage par score, redaction "
        "assistee, relecture humaine avant mise en ligne."
    )
    lignes.append("")
    lignes.append(f"{nb_flux} entrees actives, mise a jour plusieurs fois par semaine.")
    lignes.append("")
    lignes.append("djidonou.com/frontiere")
    lignes.append("")
    lignes.append("---")
    lignes.append("")
    numero += 1

    lignes.append(f"## Diapositive {numero}, question de cloture")
    lignes.append("")
    lignes.append(
        f"{A_COMPLETER} : une question ouverte qui appelle une reponse en "
        "commentaire, pas une formule de politesse."
    )
    lignes.append("")
    lignes.append("---")
    lignes.append("")

    lignes.append("# Texte du post")
    lignes.append("")
    lignes.append(
        f"{A_COMPLETER} : trois a cinq phrases qui portent la these, sans "
        "reprendre les diapositives mot pour mot. Le lien vers la veille en "
        "fin de texte, LinkedIn penalisant les liens sortants places en tete."
    )
    lignes.append("")
    lignes.append(f"Veille complete : {PAGE}")
    lignes.append("")

    lignes.append("# Sources")
    lignes.append("")
    for item in items:
        lignes.append(f"- {item.get('titre', '')}. {reference(item)}. {item.get('url', '')}")
    lignes.append("")

    lignes.append("# A verifier avant publication")
    lignes.append("")
    modeles = modeles_utilises(items)
    mention = ", ".join(modeles) if modeles else "modele non renseigne"
    lignes.append(
        f"Les resumes ci-dessus sont rediges par un modele de langage "
        f"({mention}), pas par une lecture des articles. Confirme a la source "
        "tout chiffre, tout nom et tout enonce de resultat avant de le publier "
        "sous ton nom."
    )
    lignes.append("")
    return "\n".join(lignes)


def main(date=None):
    items = items_publies(charger(CURES, []), charger(FLUX, []))
    signal, _ = separer_signal(items)
    if not signal:
        print("Aucun signal publie par cette execution : pas de carrousel.")
        for fichier in (SORTIE, SORTIE_TITRE):
            if fichier.exists():
                fichier.unlink()
        return 0

    date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nb_flux = len(charger(FLUX, []))
    texte = rendre(items, date, nb_flux)

    DOSSIER.mkdir(exist_ok=True)
    plan = DOSSIER / f"{date}-frontiere.md"
    # Deux executions peuvent tomber le meme jour (c'est arrive les 17 et 24
    # aout). La seconde ecraserait un plan deja retravaille, et le travail
    # editorial serait perdu sans que rien ne le dise. Le squelette ne
    # remplace donc jamais un fichier existant.
    if plan.exists():
        print(f"{plan} existe deja : conserve tel quel, squelette non ecrit.")
    else:
        plan.write_text(texte, encoding="utf-8")
        print(f"Carrousel a valider ecrit dans {plan} ({len(items)} item(s)).")
    SORTIE.write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")
    SORTIE_TITRE.write_text(rendre_titre(date), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
