"""Publication pour La Frontiere.

Lit pipeline/_candidats_cures.json, fusionne avec frontiere/data/flux.json
existant et pipeline/_candidats_archives.json, deduplique, applique une
fenetre glissante de 90 jours et un seuil de selection principale, designe le
signal de la semaine, et ecrit :
  - frontiere/data/flux.json
  - frontiere/data/meta.json
  - frontiere/data/archives/AAAA-MM.json
  - frontiere/feed.xml
  - sitemap.xml (date de mise a jour de /frontiere/ uniquement)

Valide chaque JSON avant ecriture : si le resultat est mal forme ou vide
alors que l'entree ne l'etait pas, le script s'arrete sans rien ecrire
(la page garde l'etat precedent plutot que de casser).
"""

import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
DONNEES = RACINE / "frontiere" / "data"
ARCHIVES = DONNEES / "archives"
CURES = Path(__file__).parent / "_candidats_cures.json"
CANDIDATS_ARCHIVES = Path(__file__).parent / "_candidats_archives.json"
SITEMAP = RACINE / "sitemap.xml"
FRONTIERE_INDEX = RACINE / "frontiere" / "index.html"

FENETRE_JOURS = 90
SEUIL_SELECTION_PRINCIPALE = 3

# Le signal se choisissait parmi les 90 jours de la fenetre, sans contrainte
# de fraicheur : le mieux note y restait signal jusqu'a sortir de la fenetre.
# Constate le 17 aout 2026, un article du 10 aout tenait la place depuis une
# semaine et l'aurait tenue deux mois de plus, faute d'un score superieur.
# « Signal de la semaine » decrivait alors un classement trimestriel.
#
# Le choix se fait desormais par paliers de fraicheur decroissante (voir
# designer_signal) : les items rapportes par l'execution en cours, sinon les
# 7 derniers jours, sinon la fenetre entiere. Les paliers ne servent qu'a
# couvrir une execution vide, jamais a rattraper un score faible : sans quoi
# le repli ressusciterait l'ancien signal, c'est-a-dire le defaut corrige ici.
FENETRE_SIGNAL_JOURS = 7

# Plancher sous lequel aucun signal n'est designe, la page expliquant alors
# qu'aucun article ne ressort du lot. Le score est le produit du nombre de
# mots-cles economiques par le nombre de mots-cles IA (pipeline/curate.py,
# score_heuristique) : 6 exige les deux dimensions franchement presentes,
# 2 x 3 au moins, soit le double du seuil de publication. Sur la selection du
# 17 aout 2026, 11 entrees sur 56 l'atteignaient.
SEUIL_SIGNAL = 6

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


def designer_signal(entrees, ids_du_run, aujourd_hui):
    """Choisit le signal de la semaine, ou None si aucun ne ressort du lot.

    Pure : ne lit ni le disque ni l'horloge, la date du jour est un argument
    pour que les tests n'aient pas a figer de date litterale.

    Trois paliers de fraicheur decroissante, le premier non vide gagne :
      1. les entrees rapportees par l'execution en cours (ids_du_run) ;
      2. a defaut, celles publiees depuis FENETRE_SIGNAL_JOURS jours ;
      3. a defaut, la fenetre entiere.
    Le palier 3 n'est atteint que par une execution sans recolte sur une
    semaine calme, cas ou reproposer le meilleur du trimestre vaut mieux que
    de vider la section.

    Le plancher SEUIL_SIGNAL s'applique au seul candidat retenu, sans repli
    sur le palier suivant : un score faible dans une recolte fraiche signifie
    que rien ne ressort cette semaine, pas qu'il faut aller rechercher plus
    vieux et mieux note.
    """
    ids = set(ids_du_run or ())
    limite = aujourd_hui - timedelta(days=FENETRE_SIGNAL_JOURS)
    paliers = (
        [e for e in entrees if e.get("id") in ids],
        [e for e in entrees if date_valide(e) >= limite],
        list(entrees),
    )
    for candidats in paliers:
        if not candidats:
            continue
        meilleur = max(
            candidats,
            key=lambda e: (e.get("score", 0), e.get("date_publication") or ""),
        )
        if meilleur.get("score", 0) < SEUIL_SIGNAL:
            return None
        return meilleur
    return None


def completer_derniere_execution(historique, aujourd_hui, signal_designe, score_max):
    """Ajoute l'issue du signal a la ligne du jour dans l'historique de sante.

    Pure : renvoie (historique, complete) sans toucher au disque.

    Le carnet est ecrit par curate.py, qui tourne avant publish.py, donc avant
    que le signal soit designe. La ligne du jour est completee sur place
    plutot que dupliquee : une seconde ligne a la meme date ferait compter
    deux executions la ou il n'y en a eu qu'une, et verifier_sante.py raisonne
    precisement sur les dernieres lignes.

    Aucune ligne n'est creee si celle du jour manque : publish.py lance seul,
    hors du workflow, n'a pas d'execution de collecte a decrire, et inventer
    une ligne a moitie vide fausserait l'historique plus qu'un trou avoue.
    """
    if not historique:
        return historique, False
    derniere = historique[-1]
    if derniere.get("date") != aujourd_hui.isoformat():
        return historique, False
    derniere["signal_designe"] = signal_designe
    # score_max porte sur la recolte du jour, pas sur la fenetre : c'est la
    # mesure qui dit si le plancher est bien calibre. Sur une execution sans
    # recolte, il n'y a rien a mesurer et le champ vaut None plutot que 0,
    # qu'on confondrait avec une recolte dont tout serait tombe a zero.
    derniere["score_max"] = score_max
    return historique, True


def enregistrer_issue_signal(signal, entrees_du_run, aujourd_hui, chemin=None):
    """Ecrit l'issue du signal dans frontiere/data/sante.json."""
    chemin = chemin or (DONNEES / "sante.json")
    if not chemin.exists():
        print("Aucun historique de sante a completer.")
        return
    try:
        historique = json.loads(chemin.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Historique de sante illisible, issue du signal non enregistree.")
        return

    scores = [e.get("score", 0) for e in entrees_du_run]
    historique, complete = completer_derniere_execution(
        historique,
        aujourd_hui,
        signal is not None,
        max(scores) if scores else None,
    )
    if not complete:
        print("Aucune ligne de sante datee de ce jour, issue du signal non enregistree.")
        return

    contenu = json.dumps(historique, ensure_ascii=False, indent=2)
    json.loads(contenu)  # validation avant ecriture
    chemin.write_text(contenu, encoding="utf-8")


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
    <description>Veille automatisee IA, economie et machine learning, selon des criteres thematiques definis par un economiste.</description>
    <language>fr-ca</language>
{corps}
  </channel>
</rss>
"""


def synchroniser_sitemap(chemin_sitemap=SITEMAP, chemin_meta=DONNEES / "meta.json"):
    """Aligne le lastmod de /frontiere/ sur la date inscrite dans meta.json."""
    meta = charger_json(chemin_meta, {})
    derniere_mise_a_jour = meta.get("derniere_mise_a_jour")
    if not derniere_mise_a_jour:
        raise ValueError("derniere_mise_a_jour absente de meta.json")
    try:
        date.fromisoformat(derniere_mise_a_jour)
    except ValueError as erreur:
        raise ValueError("derniere_mise_a_jour doit etre une date ISO") from erreur

    contenu = chemin_sitemap.read_text(encoding="utf-8")
    motif = re.compile(
        r"(<url>\s*<loc>https://djidonou\.com/frontiere/</loc>\s*<lastmod>)[^<]+(</lastmod>)"
    )
    contenu_modifie, nombre = motif.subn(
        lambda correspondance: (
            f"{correspondance.group(1)}{derniere_mise_a_jour}{correspondance.group(2)}"
        ),
        contenu,
        count=1,
    )
    if nombre != 1:
        raise ValueError("entree /frontiere/ introuvable ou invalide dans sitemap.xml")
    chemin_sitemap.write_text(contenu_modifie, encoding="utf-8")


def generer_jsonld_flux(entrees):
    """Une entree schema.org CreativeWork par item du flux, en JSON-LD.

    Distingue la redaction (resume_fr, angle_eco), attribuee a Ulrich
    Djidonou, du travail original cite (titre, auteurs, url externe) : sans
    cette distinction, une IA qui lit le balisage attribuerait un papier
    externe a l'auteur du site plutot qu'a ses vrais auteurs.
    """
    elements = []
    for position, entree in enumerate(entrees, start=1):
        description = entree.get("resume_fr", "")
        if entree.get("angle_eco"):
            description = f"{description} {entree['angle_eco']}".strip()
        oeuvre = {
            "@type": "CreativeWork",
            "headline": entree["titre"],
            "url": "https://djidonou.com/frontiere/",
            "datePublished": entree.get("date_publication"),
            "inLanguage": "fr",
            "author": {"@id": "https://djidonou.com/#person"},
            "description": description,
            "isPartOf": {"@id": "https://djidonou.com/frontiere/#page"},
            "citation": {
                "@type": "CreativeWork",
                "name": entree["titre"],
                "url": entree["url"],
                "author": entree.get("auteurs") or entree.get("source", ""),
            },
        }
        if entree.get("themes"):
            oeuvre["keywords"] = ", ".join(entree["themes"])
        elements.append({
            "@type": "ListItem",
            "position": position,
            "item": oeuvre,
        })

    return {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": elements,
    }


def inventorier_archives(dossier=None):
    """Renvoie (mois_non_vides, comptes) a partir des fichiers d'archives.

    Un mois sans aucune entree existe comme fichier mais n'est pas une
    archive : le lister donnait un bouton cliquable menant a un ecran vide,
    ce qu'un visiteur lit comme une panne. C'est le cas de 2026-06.json, qui
    contient une liste vide depuis sa creation.

    Les comptes accompagnent la liste pour que le bouton annonce ce qu'il
    ouvre, plutot que d'obliger a cliquer pour le decouvrir.
    """
    dossier = dossier or ARCHIVES
    mois = []
    comptes = {}
    for chemin in sorted(dossier.glob("*.json")):
        entrees = charger_json(chemin, [])
        if not entrees:
            continue
        mois.append(chemin.stem)
        comptes[chemin.stem] = len(entrees)
    return mois, comptes


def echapper_pour_balise_script(charge_utile):
    """Neutralise le `<` d'un JSON destine a vivre entre <script> et </script>.

    json.dumps n'echappe ni `<` ni `/`. Le titre d'un item vient tel quel du
    flux RSS de la source (voir collect.py) : un titre contenant la chaine
    </script> fermerait la balise et le reste passerait pour du HTML dans une
    page servie sur djidonou.com. Le pipeline commite ce fichier deux fois par
    semaine sans relecture humaine, donc le filtre est ici et non en aval.

    \\u003c est un echappement JSON standard : un lecteur automatise (Google,
    un LLM) relit exactement la meme valeur qu'avant.
    """
    return charge_utile.replace("<", "\\u003c")


def injecter_jsonld_flux(donnees_jsonld, chemin_index=FRONTIERE_INDEX):
    """Ecrit le JSON-LD par item dans le script balise id="flux-jsonld"."""
    contenu = chemin_index.read_text(encoding="utf-8")
    motif = re.compile(
        r'(<script type="application/ld\+json" id="flux-jsonld">\s*).*?(\s*</script>)',
        re.DOTALL,
    )
    charge_utile = echapper_pour_balise_script(
        json.dumps(donnees_jsonld, ensure_ascii=False, indent=2)
    )
    contenu_modifie, nombre = motif.subn(
        lambda correspondance: (
            f"{correspondance.group(1)}{charge_utile}{correspondance.group(2)}"
        ),
        contenu,
        count=1,
    )
    if nombre != 1:
        raise ValueError("bloc flux-jsonld introuvable dans frontiere/index.html")
    chemin_index.write_text(contenu_modifie, encoding="utf-8")


def repartir_selection_et_archives(entrees, limite):
    """Separe la selection recente des items anciens ou sous le seuil."""
    selection = []
    archives = []
    for entree in entrees:
        if (
            date_valide(entree) >= limite
            and entree.get("score", 0) >= SEUIL_SELECTION_PRINCIPALE
        ):
            selection.append(entree)
        else:
            archives.append(entree)
    return selection, archives


def main():
    DONNEES.mkdir(parents=True, exist_ok=True)
    ARCHIVES.mkdir(parents=True, exist_ok=True)

    nouveaux = charger_json(CURES, [])
    nouveaux_archives = charger_json(CANDIDATS_ARCHIVES, [])
    flux_existant = charger_json(DONNEES / "flux.json", [])

    fusion = {entree["id"]: entree for entree in flux_existant}
    for entree in nouveaux + nouveaux_archives:
        fusion[entree["id"]] = entree

    aujourd_hui = date.today()
    limite = aujourd_hui - timedelta(days=FENETRE_JOURS)

    dans_fenetre, a_archiver = repartir_selection_et_archives(
        fusion.values(),
        limite,
    )

    entrees_par_mois = {}
    for entree in a_archiver:
        entrees_par_mois.setdefault(
            date_valide(entree).strftime("%Y-%m"),
            [],
        ).append(entree)

    for mois, entrees in entrees_par_mois.items():
        chemin_archive = ARCHIVES / f"{mois}.json"
        archive = charger_json(chemin_archive, [])
        identifiants_archives = {entree["id"] for entree in archive}
        archive.extend(
            entree for entree in entrees
            if entree["id"] not in identifiants_archives
        )
        archive.sort(key=lambda e: e.get("date_publication") or "", reverse=True)
        contenu = json.dumps(archive, ensure_ascii=False, indent=2)
        json.loads(contenu)  # validation avant ecriture
        chemin_archive.write_text(contenu, encoding="utf-8")

    dans_fenetre.sort(key=lambda e: e.get("date_publication") or "", reverse=True)

    for entree in dans_fenetre:
        entree["signal"] = False
    # Les ids du run : les items cures a cette execution. Les candidats
    # d'archive en sont exclus, ils sortent deja de la fenetre par leur date.
    ids_du_run = [entree["id"] for entree in nouveaux]
    signal = designer_signal(dans_fenetre, ids_du_run, aujourd_hui)
    if signal is not None:
        signal["signal"] = True

    # Mesure sur les seuls items du run qui pouvaient devenir signal, donc
    # ceux tombes dans la fenetre : un candidat d'archive n'y prete pas.
    entrees_du_run = [e for e in dans_fenetre if e.get("id") in set(ids_du_run)]

    contenu_flux = json.dumps(dans_fenetre, ensure_ascii=False, indent=2)
    json.loads(contenu_flux)  # validation avant ecriture

    if flux_existant and not dans_fenetre:
        print("ATTENTION : le nouveau flux serait vide alors que l'ancien ne l'etait pas. Abandon sans ecriture.")
        return

    (DONNEES / "flux.json").write_text(contenu_flux, encoding="utf-8")
    injecter_jsonld_flux(generer_jsonld_flux(dans_fenetre))

    compte_par_theme = {theme: 0 for theme in THEMES_CONNUS}
    for entree in dans_fenetre:
        for theme in entree.get("themes", []):
            if theme in compte_par_theme:
                compte_par_theme[theme] += 1

    mois_archives, compte_par_archive = inventorier_archives()
    meta = {
        "derniere_mise_a_jour": aujourd_hui.isoformat(),
        "nb_entrees_flux": len(dans_fenetre),
        "compte_par_theme": compte_par_theme,
        "mois_archives": mois_archives,
        "compte_par_archive": compte_par_archive,
    }
    contenu_meta = json.dumps(meta, ensure_ascii=False, indent=2)
    json.loads(contenu_meta)
    (DONNEES / "meta.json").write_text(contenu_meta, encoding="utf-8")
    synchroniser_sitemap()

    feed = generer_feed_rss(dans_fenetre)
    (RACINE / "frontiere" / "feed.xml").write_text(feed, encoding="utf-8")

    print(f"Flux publie : {len(dans_fenetre)} entrees, {len(a_archiver)} archivees.")
    enregistrer_issue_signal(signal, entrees_du_run, aujourd_hui)

    if signal is not None:
        print(f"Signal de la semaine : {signal['titre']} (score {signal.get('score', 0)})")
    else:
        print(
            f"Signal de la semaine : aucun, aucun article n'atteint le score "
            f"{SEUIL_SIGNAL} parmi les {len(ids_du_run)} rapportes."
        )


if __name__ == "__main__":
    main()
