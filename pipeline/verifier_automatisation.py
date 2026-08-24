"""Controle d'etat des deux automatisations de La Frontiere.

Repond a trois questions qui ne peuvent se verifier qu'apres coup, une fois
qu'une execution planifiee a eu lieu :

  1. le rattrapage (regenerer-flux) progresse-t-il, et notifie-t-il ?
  2. la veille (frontiere) publie-t-elle toujours ?
  3. les revues AEA franchissent-elles enfin la collecte ?

Lecture seule : rien n'est ecrit, ni dans le depot ni sur GitHub. Le script
interroge l'API GitHub avec gh, deja authentifie sur le poste de l'auteur.

    python -m pipeline.verifier_automatisation

Sort en 0 si tout est conforme, en 1 si au moins un controle echoue, de sorte
que le resultat soit exploitable dans un enchainement de commandes.
"""

import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
FLUX = RACINE / "frontiere" / "data" / "flux.json"
DEPOT = "ulrich-e-r-djidonou/ulrich-e-r-djidonou.github.io"
# Le modele qui a redige les textes d'origine. Tant qu'un item le porte
# encore, c'est que le rattrapage ne l'a pas atteint.
MODELE_ORIGINE = "qwen2.5:3b"


def gh_json(*arguments):
    """Appelle gh et retourne le JSON, ou None si l'appel echoue."""
    try:
        sortie = subprocess.run(
            ["gh", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    try:
        return json.loads(sortie.stdout)
    except json.JSONDecodeError:
        return None


def derniere_execution(workflow):
    runs = gh_json(
        "run", "list", "--repo", DEPOT, "--workflow", workflow, "-L", "1",
        "--json", "databaseId,conclusion,createdAt,event,headSha",
    )
    return runs[0] if runs else None


def git(*arguments):
    """Commande git locale, ou None si elle echoue."""
    try:
        sortie = subprocess.run(
            ["git", *arguments],
            cwd=RACINE,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return sortie.stdout.strip() if sortie.returncode == 0 else None


def execute_le_workflow_actuel(run, chemin_workflow):
    """Le run a-t-il tourne sur une version a jour du fichier de workflow ?

    Sans ce controle, renommer une etape ferait passer toutes les etapes
    attendues pour manquantes dans les executions anterieures, et le script
    signalerait des pannes qui n'existent pas.
    """
    dernier = git("log", "--format=%H", "-1", "--", chemin_workflow)
    sha = (run or {}).get("headSha")
    if not dernier or not sha:
        return True
    if git("cat-file", "-e", f"{sha}^{{commit}}") is None:
        return True
    return git("merge-base", "--is-ancestor", dernier, sha) is not None


def etapes(run_id):
    """Retourne {nom d'etape: conclusion} pour une execution donnee."""
    donnees = gh_json("run", "view", str(run_id), "--repo", DEPOT, "--json", "jobs")
    if not donnees:
        return {}
    return {
        etape["name"]: etape["conclusion"]
        for job in donnees.get("jobs", [])
        for etape in job.get("steps", [])
    }


def charger_flux():
    contenu = json.loads(FLUX.read_text(encoding="utf-8"))
    return contenu["items"] if isinstance(contenu, dict) else contenu


def controler_rattrapage(anomalies):
    print("1. Rattrapage des textes (regenerer-flux)")
    run = derniere_execution("regenerer-flux.yml")
    if not run:
        print("   Aucune execution trouvee. Le workflow n'a jamais tourne.")
        anomalies.append("regenerer-flux n'a jamais tourne")
        return

    print(f"   Derniere execution : {run['createdAt'][:16]} ({run['event']}), "
          f"conclusion {run['conclusion']}, commit {run.get('headSha', '?')[:7]}")

    if not execute_le_workflow_actuel(run, ".github/workflows/regenerer-flux.yml"):
        print("   Cette execution est anterieure a la version actuelle du "
              "workflow : ses etapes ne sont pas comparables.")
        print("   Rien a conclure avant la prochaine execution planifiee.")
        return

    detail = etapes(run["databaseId"])

    # Le workflow a deux modes exclusifs depuis le 19 aout 2026 : la reecriture
    # du francais et le rattrapage des champs anglais. Chacun saute l'etape de
    # l'autre par construction. Exiger les deux ferait crier l'anomalie a
    # chaque execution, quel que soit le mode, et un controle qui alerte
    # toujours n'alerte plus.
    redaction_fr = "Rediger le lot du jour, dans la limite du quota"
    redaction_en = "Completer les champs anglais du lot du jour"
    mode_anglais = detail.get(redaction_en) == "success"
    if mode_anglais:
        print("   Mode anglais : l'etape de reecriture francaise est sautee, "
              "c'est attendu.")

    attendus = [
        (redaction_en if mode_anglais else redaction_fr, "success"),
        ("Sauvegarder la relecture pour l'execution suivante", "success"),
        ("Appliquer les textes valides", "success"),
        ("Committer si le flux a change", "success"),
    ]
    for nom, attendu in attendus:
        obtenu = detail.get(nom, "absente")
        marque = "ok" if obtenu == attendu else "ECHEC"
        print(f"   [{marque}] {nom} : {obtenu}")
        if obtenu != attendu:
            anomalies.append(f"etape '{nom}' en {obtenu}")

    nom_notification = (
        "Notifier les champs anglais ajoutes"
        if mode_anglais
        else "Notifier ce qui vient d'etre publie"
    )
    notification = detail.get(nom_notification, "absente")
    print(f"   Notification : {notification} "
          "(skipped est normal s'il n'y avait rien de neuf)")


def controler_progression(anomalies):
    print("\n2. Progression de la reecriture")
    items = charger_flux()
    restants = [i for i in items if i.get("llm") == MODELE_ORIGINE]
    reecrits = len(items) - len(restants)
    print(f"   {reecrits}/{len(items)} items reecrits, {len(restants)} restants.")
    if restants:
        print(f"   Modeles presents : "
              f"{sorted({i.get('llm', 'inconnu') for i in items})}")
    else:
        print("   Rattrapage termine : plus aucun item du modele d'origine.")


def controler_veille(anomalies):
    print("\n3. Veille hebdomadaire (frontiere)")
    run = derniere_execution("frontiere.yml")
    if not run:
        print("   Aucune execution trouvee.")
        anomalies.append("frontiere n'a jamais tourne")
        return
    print(f"   Derniere execution : {run['createdAt'][:16]}, "
          f"conclusion {run['conclusion']}")
    if run["conclusion"] != "success":
        anomalies.append(f"derniere veille en {run['conclusion']}")


def controler_aea(anomalies):
    print("\n4. Revues AEA dans le flux publie")
    items = charger_flux()
    aea = [i for i in items if "American Economic" in (i.get("source") or "")]
    if aea:
        print(f"   {len(aea)} item(s) AEA publie(s) :")
        for item in aea:
            print(f"   - {item.get('date_publication')} {item['titre'][:70]}")
    else:
        print("   Aucun item AEA publie pour l'instant.")
        print("   Attendu : la source est active depuis le 2 aout 2026 et les "
              "DOI du JEP ete 2026 ont ete enregistres chez Crossref le 3 aout.")


def main():
    if gh_json("api", "user", "--jq", "{login: .login}") is None:
        print("gh indisponible ou non authentifie. Lancer : gh auth login",
              file=sys.stderr)
        return 1

    anomalies = []
    controler_rattrapage(anomalies)
    controler_progression(anomalies)
    controler_veille(anomalies)
    controler_aea(anomalies)

    print("\n" + "-" * 60)
    if anomalies:
        print(f"{len(anomalies)} anomalie(s) :")
        for anomalie in anomalies:
            print(f"  - {anomalie}")
        return 1
    print("Tout est conforme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
