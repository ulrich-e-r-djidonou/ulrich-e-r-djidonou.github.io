"""Signale les depots dont l'automatisation ne tourne plus.

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

Le perimetre depend du jeton fourni :

- `JETON_DEPOTS`, un jeton personnel, couvre aussi les depots prives. C'est
  la seule facon de surveiller `gtrends`, ou vit la chaine ICIE, et les
  autres depots fermes : le jeton d'un run GitHub ne voit pas au-dela de son
  propre depot.
- Sans lui, le controle retombe sur les depots publics et le dit en clair
  dans son rapport, plutot que d'annoncer une couverture qu'il n'a pas.

Ce controle tourne dans un depot public, dont les journaux d'execution sont
lisibles par n'importe qui. Les depots prives y apparaissent donc numerotes,
sans leur nom ni celui de leur automatisation : le signal (« quelque chose
est casse ») remonte sans publier le detail de projets fermes. En local,
`AFFICHER_NOMS_PRIVES=1` reaffiche les noms.

    python -m pipeline.verifier_workflows
    python -m pipeline.verifier_workflows --rapport-seul   # n'echoue jamais
    AFFICHER_NOMS_PRIVES=1 python -m pipeline.verifier_workflows
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
    "dependency graph",
    "dependabot updates",
    # Ce controle lui-meme : il echoue exactement quand il trouve quelque
    # chose, puisque l'echec est le mecanisme d'alerte. Se signaler soi-meme
    # ajouterait une ligne de bruit a chaque rapport non vide.
    "verifier-workflows",
)

# Le deploiement Pages ne se declenche jamais par cron : son evenement est
# `dynamic`, produit par un push ou par l'API. Le filtrer sur `schedule`,
# comme le reste, revenait a ne jamais le regarder. Il a ainsi echoue le
# 6 aout 2026 sans que rien ne le dise, alors qu'un deploiement rate laisse
# le site servir la version precedente : la panne est invisible cote
# visiteur, et c'est exactement ce que ce controle doit rattraper.
#
# Deux orthographes : l'API nomme le workflow `pages-build-deployment`,
# tandis que chaque execution s'intitule « pages build and deployment ».
# L'ancienne liste des ignores ne portait que la seconde, donc elle ne
# correspondait a rien ; le workflow n'etait pas ignore, il etait
# simplement invisible faute d'execution planifiee. Retenir les deux evite
# de refaire l'erreur si GitHub change celle qu'il expose.
NOMS_PAGES = frozenset({"pages-build-deployment", "pages build and deployment"})


def est_workflow_pages(titre):
    return titre.strip().lower() in NOMS_PAGES


def evenement_surveille(titre):
    """Evenement dont la derniere execution fait foi pour ce workflow.

    Pour tout le reste, seules les executions planifiees comptent : un
    lancement manuel rate est deja sous les yeux de celui qui l'a lance, et
    un essai manuel ancien masquerait l'etat reel du cron. Pages n'a pas de
    cron du tout, donc son dernier deploiement fait foi quel qu'il soit.
    """
    return None if est_workflow_pages(titre) else "schedule"


def jeton_personnel():
    """Jeton personnel eventuel, seul a donner acces aux depots prives."""
    return os.environ.get("JETON_DEPOTS", "").strip()


def entetes():
    """Le jeton personnel prime : sans lui, celui du run ne voit que le public."""
    jeton = jeton_personnel() or os.environ.get("GITHUB_TOKEN", "")
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


def source_depots(avec_jeton_personnel):
    """Chemin et parametres d'API selon l'etendue que le jeton autorise.

    `/user/repos` renvoie les depots prives autant que publics, mais exige un
    jeton personnel : appele avec le jeton d'un run, il repond 401 ou 403.
    `/users/{proprietaire}/repos` accepte n'importe quel jeton et ne renvoie
    que le public. Choisir le mauvais chemin ferait echouer le controle ou
    lui ferait manquer la moitie des depots en silence.
    """
    if avec_jeton_personnel:
        return "/user/repos", {"affiliation": "owner", "sort": "pushed"}
    return f"/users/{PROPRIETAIRE}/repos", {"type": "owner", "sort": "pushed"}


def depots_du_proprietaire(avec_jeton_personnel=None):
    if avec_jeton_personnel is None:
        avec_jeton_personnel = bool(jeton_personnel())
    chemin, parametres = source_depots(avec_jeton_personnel)
    depots = []
    page = 1
    while True:
        lot = api(chemin, per_page=100, page=page, **parametres)
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


def reparee_depuis(chemin_complet, workflow_id, date_echec):
    """Vrai si une execution a reussi apres l'echec, quel qu'en soit le declencheur."""
    reussites = api(
        f"/repos/{chemin_complet}/actions/workflows/{workflow_id}/runs",
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


def noms_prives_affichables():
    """Vrai si le journal peut porter les noms des depots prives.

    Ce controle tourne dans un depot public, dont les journaux d'execution
    sont lisibles par n'importe qui. Nommer un depot prive en echec y
    publierait son nom, celui de son automatisation et le fait qu'elle est
    cassee : de quoi renseigner un inconnu sur des projets fermes. En local,
    ou l'auteur est le seul lecteur, il n'y a rien a masquer.
    """
    return bool(os.environ.get("AFFICHER_NOMS_PRIVES", "").strip())


def etiquette_depot(depot, rang_prive):
    """Nom a afficher : masque pour un depot prive, sauf en local."""
    if not depot.get("private"):
        return depot["name"]
    if noms_prives_affichables():
        return f"{depot['name']} (prive)"
    return f"depot prive {rang_prive}"


def examiner_depot(depot, rang_prive=1):
    """Retourne la liste des problemes trouves sur un depot."""
    problemes = []
    # Un jeton personnel peut ramener des depots qui ne sont pas sous
    # PROPRIETAIRE. Passer par full_name evite d'interroger un chemin qui
    # n'existe pas et de compter le depot comme sans automatisation.
    chemin = depot.get("full_name") or f"{PROPRIETAIRE}/{depot['name']}"
    nom = etiquette_depot(depot, rang_prive)
    prive_masque = depot.get("private") and not noms_prives_affichables()

    try:
        workflows = api(f"/repos/{chemin}/actions/workflows",
                        per_page=100).get("workflows", [])
    except requests.HTTPError:
        # Actions desactive sur le depot : rien a surveiller.
        return problemes

    for workflow in workflows:
        titre_reel = workflow.get("name", "")
        if titre_reel.lower() in WORKFLOWS_IGNORES:
            continue
        est_pages = est_workflow_pages(titre_reel)
        # Le nom d'un workflow decrit ce qu'il fait, donc ce que fait le
        # projet : le masquer avec celui du depot, sinon le masquage ne
        # protege rien. Pages garde son nom : il est identique partout et
        # ne revele rien du projet.
        titre = titre_reel if est_pages or not prive_masque else "automatisation"

        etat = workflow.get("state", "")
        if etat.startswith("disabled"):
            problemes.append((nom, titre, f"workflow desactive ({etat})"))
            continue

        evenement = evenement_surveille(titre_reel)
        parametres = {"per_page": 1}
        if evenement:
            parametres["event"] = evenement
        executions = api(
            f"/repos/{chemin}/actions/workflows/{workflow['id']}/runs",
            **parametres,
        ).get("workflow_runs", [])

        if not executions:
            continue

        derniere = executions[0]
        if derniere.get("conclusion") == "failure":
            # Un correctif se valide en relancant le workflow a la main, sans
            # attendre le prochain cron. Sans cette verification, un workflow
            # repare resterait signale jusqu'a sa prochaine echeance, parfois
            # un mois plus tard, et le rapport perdrait sa credibilite.
            if not reparee_depuis(chemin, workflow["id"], derniere.get("created_at")):
                motif = (
                    "dernier deploiement en echec, le site sert la version "
                    "precedente"
                    if est_pages
                    else "derniere execution planifiee en echec"
                )
                problemes.append((nom, titre, motif))
            continue

        if est_pages:
            # Pas de controle de silence sur Pages : un depot sans commit
            # depuis des mois n'a aucun deploiement a montrer, et c'est
            # normal. Seul un echec non repare compte.
            continue

        lancee = horodatage(derniere.get("created_at"))
        if lancee:
            age = (datetime.now(timezone.utc) - lancee).days
            if age > SILENCE_MAX_JOURS:
                problemes.append(
                    (nom, titre, f"aucune execution planifiee depuis {age} jours")
                )

    return problemes


def resume_perimetre(depots, avec_jeton_personnel):
    """Phrase d'entete du rapport, qui dit ce qui n'est pas couvert."""
    if not avec_jeton_personnel:
        return (
            f"{len(depots)} depots publics examines. Les depots prives ne sont "
            "pas couverts : definir le secret JETON_DEPOTS pour les inclure."
        )
    if noms_prives_affichables():
        prives = sum(1 for depot in depots if depot.get("private"))
        return f"{len(depots)} depots examines, dont {prives} prives."
    # Le decompte des depots prives n'apparait pas dans un journal public :
    # le total suffit a confirmer que le jeton a bien elargi le perimetre.
    return (
        f"{len(depots)} depots examines, publics et prives. Noms des depots "
        "prives masques ; relancer en local avec AFFICHER_NOMS_PRIVES=1 pour "
        "les voir."
    )


def main():
    rapport_seul = "--rapport-seul" in sys.argv
    avec_jeton_personnel = bool(jeton_personnel())

    depots = depots_du_proprietaire(avec_jeton_personnel)
    print(resume_perimetre(depots, avec_jeton_personnel))

    problemes = []
    rang_prive = 0
    for depot in depots:
        if depot.get("private"):
            rang_prive += 1
        problemes += examiner_depot(depot, rang_prive)

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
