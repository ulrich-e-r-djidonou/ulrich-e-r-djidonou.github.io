"""Tient a jour l'etiquette de fraicheur des cartes de projets.

La carte ICIE annoncait « Donnees jusqu'au 2 aout 2026 », ecrit a la main
dans `projets.html`. Tant que l'indice se rafraichissait a la main, la date
suivait. Des que le rafraichissement devient planifie, elle ne suit plus :
l'indice avance, la carte reste, et le site affiche une date fausse sans que
rien ne le signale. Une carte qui ment sur sa fraicheur est pire qu'une carte
sans date, parce qu'elle est credible.

Ce module fait de `data/projets.json` la source unique de ces etiquettes, la
remplit depuis ce que chaque projet publie reellement, et regenere le
fragment correspondant de `projets.html`. La date affichee ne peut plus etre
en avance sur la donnee : elle en descend.

Pour ICIE, deux sources, dans l'ordre :

1. `etat.json`, ecrit a cote du dashboard par la publication ICIE. Contrat
   stable, deux cents octets.
2. A defaut, le JSON embarque dans le dashboard lui-meme, dont le champ
   `recent.latestDate` porte la derniere date de donnees. Ce repli couvre la
   periode ou `etat.json` n'existe pas encore, et le cas ou une publication
   l'oublierait.

    python -m pipeline.etat_projets
    python -m pipeline.etat_projets --rapport-seul   # n'echoue jamais
"""

import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).resolve().parent.parent
FICHIER_ETATS = RACINE / "data" / "projets.json"
FICHIER_PAGE = RACINE / "projets.html"
TIMEOUT = 30

MOIS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)

# Projets dont l'etiquette suit une donnee qui bouge. Les autres cartes
# annoncent un perimetre fixe (« Donnees 2023 et 2024 ») ou une cadence
# (« Mise a jour automatique, quotidienne ») : rien a rafraichir, donc rien
# a surveiller ici.
SOURCES = {
    "icie": {
        "etat_json": "https://ulrich-e-r-djidonou.github.io/icie-dashboard/etat.json",
        "page": "https://ulrich-e-r-djidonou.github.io/icie-dashboard/",
        "gabarit": "Données jusqu'au {date}",
    },
}


def formater_date_francaise(iso):
    """2026-08-02 devient « 2 août 2026 », comme sur le reste du site."""
    jour = date.fromisoformat(iso)
    numero = "1er" if jour.day == 1 else str(jour.day)
    return f"{numero} {MOIS[jour.month - 1]} {jour.year}"


def date_depuis_etat_json(charge):
    """Lit la date de donnees dans le contrat publie par le projet."""
    valeur = charge.get("date_donnees") or charge.get("derniere_donnee")
    if not valeur:
        raise ValueError("etat.json sans champ de date de donnees")
    return str(valeur)[:10]


def date_depuis_dashboard(html):
    """Repli : la derniere date vit dans le JSON embarque du dashboard."""
    trouve = re.search(
        r'<script id="dashboard-data" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    if not trouve:
        raise ValueError("dashboard sans bloc dashboard-data")
    charge = json.loads(trouve.group(1))
    valeur = charge.get("recent", {}).get("latestDate")
    if not valeur:
        raise ValueError("dashboard sans recent.latestDate")
    return str(valeur)[:10]


def lire_source(source, recuperer=None):
    """Retourne (date_iso, origine) pour un projet, ou leve une exception."""
    recuperer = recuperer or _recuperer
    try:
        return date_depuis_etat_json(json.loads(recuperer(source["etat_json"]))), "etat.json"
    except (requests.RequestException, ValueError, KeyError):
        # Le repli existe pour la periode ou etat.json n'a pas encore ete
        # publie. Sans lui, la premiere execution planifiee echouerait sur un
        # 404 previsible et ne dirait rien d'utile.
        return date_depuis_dashboard(recuperer(source["page"])), "dashboard"


def _recuperer(url):
    reponse = requests.get(url, timeout=TIMEOUT)
    reponse.raise_for_status()
    return reponse.text


def charger_etats(chemin=FICHIER_ETATS):
    if not Path(chemin).exists():
        return {"projets": {}}
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def appliquer_etats(html, projets):
    """Reecrit le texte de chaque `<p class="project-etat" data-projet="...">`.

    Le remplacement est ancre sur l'attribut `data-projet`, pas sur le texte
    en place : une etiquette deja fausse doit pouvoir etre corrigee, et le
    script ne doit pas dependre de ce qu'il a ecrit la fois precedente.
    """
    manquants = []
    for identifiant, etat in sorted(projets.items()):
        texte = etat.get("etat", "")
        if not texte:
            continue
        motif = re.compile(
            rf'(<p class="project-etat" data-projet="{re.escape(identifiant)}"[^>]*>)'
            rf"(.*?)(</p>)",
            re.S,
        )
        html, remplaces = motif.subn(
            lambda trouve: trouve.group(1) + texte + trouve.group(3), html
        )
        if not remplaces:
            manquants.append(identifiant)
    return html, manquants


def ecrire_etats(projets, chemin=FICHIER_ETATS):
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    contenu = {
        "derniere_verification": datetime.now(timezone.utc).date().isoformat(),
        "projets": dict(sorted(projets.items())),
    }
    Path(chemin).write_text(
        json.dumps(contenu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return contenu


def main():
    rapport_seul = "--rapport-seul" in sys.argv

    etats = charger_etats()
    projets = etats.get("projets", {})
    echecs = []

    for identifiant, source in sorted(SOURCES.items()):
        try:
            iso, origine = lire_source(source)
        except Exception as erreur:  # noqa: BLE001 - le motif exact importe peu
            # La valeur precedente est conservee : un incident reseau ne doit
            # pas effacer une etiquette juste. L'echec du run porte l'alerte.
            echecs.append((identifiant, str(erreur)))
            print(f"{identifiant} : source illisible ({erreur})")
            continue
        precedent = projets.get(identifiant, {}).get("date_donnees")
        projets[identifiant] = {
            "etat": source["gabarit"].format(date=formater_date_francaise(iso)),
            "date_donnees": iso,
            "source": source["etat_json"],
        }
        mouvement = "inchange" if precedent == iso else f"{precedent} -> {iso}"
        print(f"{identifiant} : {iso} (via {origine}, {mouvement})")

    ecrire_etats(projets)

    page = FICHIER_PAGE.read_text(encoding="utf-8")
    reecrite, manquants = appliquer_etats(page, projets)
    if reecrite != page:
        FICHIER_PAGE.write_text(reecrite, encoding="utf-8")
        print(f"{FICHIER_PAGE.name} mis a jour.")
    else:
        print(f"{FICHIER_PAGE.name} deja a jour.")

    for identifiant in manquants:
        # Une carte renommee ou supprimee laisserait le JSON avancer pendant
        # que la page affiche une vieille date : le signaler evite ce silence.
        echecs.append((identifiant, "aucune carte data-projet correspondante"))
        print(f"{identifiant} : aucune carte data-projet correspondante dans la page")

    if not echecs:
        print("Etiquettes de fraicheur a jour.")
        return 0
    return 0 if rapport_seul else 1


if __name__ == "__main__":
    raise SystemExit(main())
