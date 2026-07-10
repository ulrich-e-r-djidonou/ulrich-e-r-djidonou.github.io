"""Publication pour La Frontiere.

Lit pipeline/_candidats_cures.json, fusionne avec frontiere/data/flux.json
existant, deduplique, applique une fenetre glissante de 90 jours (les
entrees plus vieilles sont archivees par mois), designe le signal de la
semaine, et ecrit :
  - frontiere/data/flux.json
  - frontiere/data/meta.json
  - frontiere/data/archives/AAAA-MM.json
  - frontiere/feed.xml

Valide chaque JSON avant ecriture : si le resultat est mal forme ou vide
alors que l'entree ne l'etait pas, le script s'arrete sans rien ecrire
(la page garde l'etat precedent plutot que de casser).
"""

import io
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

RACINE = Path(__file__).parent.parent
DONNEES = RACINE / "frontiere" / "data"
ARCHIVES = DONNEES / "archives"
CURES = Path(__file__).parent / "_candidats_cures.json"

FENETRE_JOURS = 90
THEMES_CONNUS = [
    "inference-causale", "llm", "prevision", "travail-emploi",
    "politique-publique", "outils-recherche", "donnees", "macro-finance",
]


def charger_json(chemin, defaut):
    if chemin.exists():
        return json.loads(chemin.read_text(encoding="utf-8"))
    return defaut


def date_valide(entree):
    brute = entree.get("date_publication")
    if not brute:
        return date.today()
    try:
        return date.fromisoformat(brute)
    except ValueError:
        return date.today()


def generer_feed_rss(entrees):
    items_xml = []
    for entree in entrees[:30]:
        items_xml.append(f"""    <item>
      <title>{escape(entree['titre'])}</title>
      <link>{escape(entree['url'])}</link>
      <guid isPermaLink="false">{escape(entree['id'])}</guid>
      <pubDate>{entree['date_publication']}</pubDate>
      <description>{escape(entree.get('resume_fr', ''))}</description>
    </item>""")
    corps = "\n".join(items_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>La Frontiere - Ulrich Djidonou</title>
    <link>https://djidonou.com/frontiere/</link>
    <description>Veille IA, economie et machine learning, curatee par un economiste.</description>
    <language>fr-ca</language>
{corps}
  </channel>
</rss>
"""


def main():
    DONNEES.mkdir(parents=True, exist_ok=True)
    ARCHIVES.mkdir(parents=True, exist_ok=True)

    nouveaux = charger_json(CURES, [])
    flux_existant = charger_json(DONNEES / "flux.json", [])

    fusion = {entree["id"]: entree for entree in flux_existant}
    for entree in nouveaux:
        fusion[entree["id"]] = entree

    aujourd_hui = date.today()
    limite = aujourd_hui - timedelta(days=FENETRE_JOURS)

    dans_fenetre = []
    a_archiver = []
    for entree in fusion.values():
        if date_valide(entree) >= limite:
            dans_fenetre.append(entree)
        else:
            a_archiver.append(entree)

    for entree in a_archiver:
        mois = date_valide(entree).strftime("%Y-%m")
        chemin_archive = ARCHIVES / f"{mois}.json"
        archive = charger_json(chemin_archive, [])
        if not any(e["id"] == entree["id"] for e in archive):
            archive.append(entree)
        archive.sort(key=lambda e: e.get("date_publication") or "", reverse=True)
        contenu = json.dumps(archive, ensure_ascii=False, indent=2)
        json.loads(contenu)  # validation avant ecriture
        chemin_archive.write_text(contenu, encoding="utf-8")

    dans_fenetre.sort(key=lambda e: e.get("date_publication") or "", reverse=True)

    for entree in dans_fenetre:
        entree["signal"] = False
    if dans_fenetre:
        meilleur = max(dans_fenetre, key=lambda e: (e.get("score", 0), e.get("date_publication") or ""))
        meilleur["signal"] = True

    contenu_flux = json.dumps(dans_fenetre, ensure_ascii=False, indent=2)
    json.loads(contenu_flux)  # validation avant ecriture

    if flux_existant and not dans_fenetre:
        print("ATTENTION : le nouveau flux serait vide alors que l'ancien ne l'etait pas. Abandon sans ecriture.")
        return

    (DONNEES / "flux.json").write_text(contenu_flux, encoding="utf-8")

    compte_par_theme = {theme: 0 for theme in THEMES_CONNUS}
    for entree in dans_fenetre:
        for theme in entree.get("themes", []):
            if theme in compte_par_theme:
                compte_par_theme[theme] += 1

    meta = {
        "derniere_mise_a_jour": aujourd_hui.isoformat(),
        "nb_entrees_flux": len(dans_fenetre),
        "compte_par_theme": compte_par_theme,
        "mois_archives": sorted(p.stem for p in ARCHIVES.glob("*.json")),
    }
    contenu_meta = json.dumps(meta, ensure_ascii=False, indent=2)
    json.loads(contenu_meta)
    (DONNEES / "meta.json").write_text(contenu_meta, encoding="utf-8")

    feed = generer_feed_rss(dans_fenetre)
    (RACINE / "frontiere" / "feed.xml").write_text(feed, encoding="utf-8")

    print(f"Flux publie : {len(dans_fenetre)} entrees, {len(a_archiver)} archivees.")
    print(f"Signal de la semaine : {meilleur['titre'] if dans_fenetre else 'aucun'}")


if __name__ == "__main__":
    main()
