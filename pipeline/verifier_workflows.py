"""Signale les depots publics dont l'automatisation ne tourne plus.

Un workflow planifie peut echouer mois apres mois sans que rien ne remonte :
GitHub envoie un courriel, qui se noie dans les autres. Trois projets ont
ainsi passe des mois a ne plus se mettre a jour, et le defaut n'a ete
decouvert qu'en lisant une notification par hasard.

Trois signaux sont surveillés :

1. Derniere execution en echec.
2. Workflow desactive, notamment par la regle des 60 jours d'inactivite que
   GitHub applique aux taches planifiees.
3. Workflow planifie qui n'a rien execute depuis trop longtemps : le cron a
   pu cesser de se declencher sans qu'aucune execution en echec ne le dise.

Ne couvre que les depots publics : le jeton fourni aux workflows GitHub ne
donne acces qu'a son propre depot et aux donnees publiques. Couvrir les
depots prives demanderait un jeton personnel stocke en secret, ce que ce
controle evite volontairement.

    python -m pipeline.verifier_workflows
    python -m pipeline.verifier_workflows --rapport-seul   # n'echoue jamais
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROPRIETAIRE = "ulrich-e-r-djidonou"
API = "https://api.github.com"
TIMEOUT = 30

# Au-dela de ce delai sans aucune execution, un workflow planifie est
# considere comme muet. Le cron mensuel le plus espace tourne tous les 30
# jours : 50 laisse une marge d'un cycle manque sans crier au loup.
SILENCE_MAX_JOURS = 50

# Workflows de maintenance geres par GitHub, hors du perimetre : leurs
# echecs relevent des mises a jour de dependances, pas de l'automatisation
# d'un projet.
WORKFLOWS_IGNORES = (
    "pages build and deployment",
    "dependency graph",
    "dependabot updates",
    # Ce controle lui-meme : il echoue exactement quand il trouve quelque
    # chose, puisque l'echec est le mecanisme d'alerte. Se signaler soi-meme
    # ajouterait une ligne de bruit a chaque rapport non vide.
    "verifier-workflows",
)


def entetes():
    """Le jeton du run suffit : seules des donnees publiques sont lues."""
    jeton = os.environ.get("GITHUB_TOKEN", "")
    entetes = {"Accept": "application/vnd.github+json"}
    if jeton:
        entetes["Authorization"] = f"Bearer {jeton}"
    return entetes


def api(chemin, **parametres):
    reponse = requests.get(
        f"{API}{chemin}", headers=entetes(), params=parametres, timeout=TIMEOUT
    )
    reponse.raise_for_status()
    return reponse.json()


def depots_publics():
    depots = []
    page = 1
    while True:
        lot = api(f"/users/{PROPRIETAIRE}/repos", per_page=100, page=page,
                  type="owner", sort="pushed")
        if not lot:
            break
        depots += [d for d in lot if not d.get("archived")]
        if len(lot) < 100:
            break
        page += 1
    return depots


def horodatage(texte):
    if not texte:
        return None
    return datetime.fromisoformat(texte.replace("Z", "+00:00"))


def reparee_depuis(depot, workflow_id, date_echec):
    """Vrai si une execution a reussi apres l'echec, quel qu'en soit le declencheur."""
    reussites = api(
        f"/repos/{PROPRIETAIRE}/{depot}/actions/workflows/{workflow_id}/runs",
        per_page=1,
        status="success",
    ).get("workflow_runs", [])
    if not reussites:
        return False
    derniere_reussite = horodatage(reussites[0].get("created_at"))
    echec = horodatage(date_echec)
    if not derniere_reussite or not echec:
        return False
    return derniere_reussite > echec


def examiner_depot(depot):
    """Retourne la liste des problemes trouves sur un depot."""
    problemes = []
    nom = depot["name"]

    try:
        workflows = api(f"/repos/{PROPRIETAIRE}/{nom}/actions/workflows",
                        per_page=100).get("workflows", [])
    except requests.HTTPError:
        # Actions desactive sur le depot : rien a surveiller.
        return problemes

    for workflow in workflows:
        titre = workflow.get("name", "")
        if titre.lower() in WORKFLOWS_IGNORES:
            continue

        etat = workflow.get("state", "")
        if etat.startswith("disabled"):
            problemes.append((nom, titre, f"workflow desactive ({etat})"))
            continue

        # Seules les executions planifiees comptent. Un lancement manuel
        # rate est deja sous les yeux de celui qui l'a lance ; c'est
        # l'automatisation qui tourne sans temoin, donc elle seule a besoin
        # d'etre surveillee. Filtrer sur l'evenement evite aussi qu'un essai
        # manuel ancien masque l'etat reel du cron.
        executions = api(
            f"/repos/{PROPRIETAIRE}/{nom}/actions/workflows/{workflow['id']}/runs",
            per_page=1,
            event="schedule",
        ).get("workflow_runs", [])

        if not executions:
            continue

        derniere = executions[0]
        if derniere.get("conclusion") == "failure":
            # Un correctif se valide en relancant le workflow a la main, sans
            # attendre le prochain cron. Sans cette verification, un workflow
            # repare resterait signale jusqu'a sa prochaine echeance, parfois
            # un mois plus tard, et le rapport perdrait sa credibilite.
            if not reparee_depuis(nom, workflow["id"], derniere.get("created_at")):
                problemes.append(
                    (nom, titre, "derniere execution planifiee en echec")
                )
            continue

        lancee = horodatage(derniere.get("created_at"))
        if lancee:
            age = (datetime.now(timezone.utc) - lancee).days
            if age > SILENCE_MAX_JOURS:
                problemes.append(
                    (nom, titre, f"aucune execution planifiee depuis {age} jours")
                )

    return problemes


def main():
    rapport_seul = "--rapport-seul" in sys.argv

    depots = depots_publics()
    print(f"{len(depots)} depots publics examines.")

    problemes = []
    for depot in depots:
        problemes += examiner_depot(depot)

    if not problemes:
        print("Aucune automatisation en panne.")
        return 0

    print(f"\n{len(problemes)} automatisation(s) a regarder :")
    largeur = max(len(nom) for nom, _, _ in problemes)
    for nom, titre, probleme in problemes:
        print(f"  {nom.ljust(largeur)}  {titre} : {probleme}")

    return 0 if rapport_seul else 1


if __name__ == "__main__":
    raise SystemExit(main())
