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

# Le workflow lance `python pipeline/publish.py`, qui met pipeline/ sur le
# chemin d'import, tandis que les tests font `from pipeline import publish`,
# qui y met la racine du depot. Les deux formes sont donc necessaires : la
# premiere seule casserait la suite de tests, la seconde seule casserait la
# publication en production, ce qui ne se verrait que le lundi suivant.
try:
    from pipeline import curate
except ImportError:  # pragma: no cover - depend du mode de lancement
    import curate

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
# Le vivier du signal est desormais la semaine (voir designer_signal) : les
# items de l'execution en cours reunis a ceux publies depuis 7 jours, dont on
# ecarte ceux deja passes en signal. C'est cette derniere exclusion qui
# garantit la rotation, une fenetre glissante seule ne suffisant pas : au 17
# aout, l'article du 10 etait encore dans les 7 jours, donc encore eligible.
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


def poids_economique_titre(titre):
    """Nombre de mots-cles economiques presents dans le seul titre.

    Importe la liste depuis curate.py plutot que d'en tenir une copie : deux
    listes de mots-cles qui derivent l'une de l'autre feraient departager le
    signal sur un vocabulaire different de celui qui l'a rendu eligible.
    """
    return sum(
        1 for mot in curate.MOTS_CLES_ECO
        if curate.mot_cle_present((titre or "").lower(), mot)
    )


def cle_signal(entree):
    """Ordre de preference entre candidats au signal, du plus fort au plus faible.

    Le score d'abord, puis le poids economique, decide le 17 aout 2026 : a
    score egal, l'article le plus economique passe devant. Le score etant le
    produit des deux comptes, un 6 vaut 2 x 3 ou 3 x 2 sans qu'on puisse les
    distinguer, alors que ces deux articles n'ont pas le meme interet pour une
    veille tenue par un economiste.

    Le titre tranche ensuite, meme motif a un cran plus fin : entre deux
    articles aussi economiques au compte global, celui dont le titre porte le
    vocabulaire economique annonce mieux la couleur en tete de page.

    La date ne sert plus qu'a departager ce que rien n'a separe, et garantit
    un ordre total : sans elle, deux entrees strictement equivalentes se
    classeraient selon leur position dans le fichier, donc selon l'ordre de
    collecte.

    nb_eco vaut 0 par defaut. Les entrees publiees avant le 17 aout 2026 ne le
    portent pas, l'abstract sur lequel il se calcule n'etant pas verse dans le
    flux. Elles ne sont donc departagees que sur leur titre, ce qui reste
    exact, faute d'etre complet.
    """
    return (
        entree.get("score", 0),
        entree.get("nb_eco", 0),
        poids_economique_titre(entree.get("titre")),
        entree.get("date_publication") or "",
    )


def designer_signal(entrees, ids_du_run, aujourd_hui):
    """Choisit le signal de la semaine, ou None si aucun ne ressort du lot.

    Pure : ne lit ni le disque ni l'horloge, la date du jour est un argument
    pour que les tests n'aient pas a figer de date litterale.

    Le vivier est la semaine, pas l'execution : les entrees rapportees par
    l'execution en cours reunies a celles publiees depuis FENETRE_SIGNAL_JOURS
    jours. La premiere version ne retenait que l'execution, ce qui rendait le
    signal otage de la derniere recolte : le 17 aout 2026, une execution
    manuelle lancee onze heures apres celle du matin n'a rapporte que deux
    items faibles et a efface un signal parfaitement valide, alors que trois
    articles a 6 dormaient dans la semaine. Une recolte maigre n'est pas une
    semaine vide.

    Les articles deja passes en signal sont ecartes, ce qui garantit la
    rotation demandee : c'est la repetition d'une semaine sur l'autre qui a
    ouvert ce chantier, et une fenetre glissante seule ne l'empeche pas, un
    article restant eligible tant qu'il n'est pas sorti des sept jours.

    A defaut de vivier, la fenetre entiere sert de repli, pour une semaine
    reellement vide plutot que simplement calme.

    Le plancher SEUIL_SIGNAL s'applique au seul candidat retenu, sans repli
    sur le palier suivant : un score faible dans un vivier frais signifie que
    rien ne ressort cette semaine, pas qu'il faut aller chercher plus vieux et
    mieux note.
    """
    ids = set(ids_du_run or ())
    limite = aujourd_hui - timedelta(days=FENETRE_SIGNAL_JOURS)
    jamais_signal = [e for e in entrees if not e.get("deja_signal")]
    paliers = (
        [
            e for e in jamais_signal
            if e.get("id") in ids or date_valide(e) >= limite
        ],
        jamais_signal,
    )
    for candidats in paliers:
        if not candidats:
            continue
        meilleur = max(candidats, key=cle_signal)
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


def synchroniser_sitemap(chemin_sitemap=None, chemin_meta=None):
    """Aligne le lastmod des deux pages de La Frontiere sur meta.json.

    Les chemins se resolvent a l'appel et non dans la signature : lies par
    defaut, ils figeraient les vrais fichiers du site des l'import, et un test
    de main() reecrirait sitemap.xml au lieu de son bac a sable.

    Les deux entrees publient le meme flux : laisser /en/frontier/ sur une date
    figee ferait mentir le sitemap des la premiere execution du cron.
    """
    chemin_sitemap = chemin_sitemap or SITEMAP
    chemin_meta = chemin_meta or (DONNEES / "meta.json")
    meta = charger_json(chemin_meta, {})
    derniere_mise_a_jour = meta.get("derniere_mise_a_jour")
    if not derniere_mise_a_jour:
        raise ValueError("derniere_mise_a_jour absente de meta.json")
    try:
        date.fromisoformat(derniere_mise_a_jour)
    except ValueError as erreur:
        raise ValueError("derniere_mise_a_jour doit etre une date ISO") from erreur

    contenu = chemin_sitemap.read_text(encoding="utf-8")
    for chemin_page in ("frontiere/", "en/frontier/"):
        # Les annotations hreflang s'intercalent entre <loc> et <lastmod> : le
        # motif doit les traverser, sinon il ne matche plus rien des qu'une
        # entree devient bilingue.
        motif = re.compile(
            r"(<url>\s*<loc>https://djidonou\.com/" + re.escape(chemin_page) + r"</loc>"
            r"(?:\s*<xhtml:link[^>]*/>)*\s*<lastmod>)[^<]+(</lastmod>)"
        )
        contenu, nombre = motif.subn(
            lambda correspondance: (
                f"{correspondance.group(1)}{derniere_mise_a_jour}{correspondance.group(2)}"
            ),
            contenu,
            count=1,
        )
        if nombre != 1:
            raise ValueError(
                f"entree /{chemin_page} introuvable ou invalide dans sitemap.xml"
            )
    chemin_sitemap.write_text(contenu, encoding="utf-8")


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


def injecter_jsonld_flux(donnees_jsonld, chemin_index=None):
    """Ecrit le JSON-LD par item dans le script balise id="flux-jsonld".

    Chemin resolu a l'appel, meme motif que synchroniser_sitemap.
    """
    chemin_index = chemin_index or FRONTIERE_INDEX
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
        # deja_signal survit au remplacement : regenerer_flux.py reecrit des
        # entrees deja publiees, et une entree rediger a nouveau reviendrait
        # sinon dans le vivier, ce qui reafficherait un article deja passe en
        # tete de page.
        ancienne = fusion.get(entree["id"])
        if ancienne and ancienne.get("deja_signal"):
            entree["deja_signal"] = True
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

    # Sans fichier de candidats, cette execution n'est pas une publication :
    # c'est publish.py lance seul, hors du pipeline. Redesigner le signal sur
    # une recolte inexistante detruit celui en place, ce qui est arrive deux
    # fois le 17 aout 2026 pendant une simple verification d'import. La
    # maintenance normale (fenetre, archives, feed, sitemap) se poursuit, seul
    # le signal est laisse intact.
    recolte_reelle = CURES.exists()
    if not recolte_reelle:
        print(
            "ATTENTION : _candidats_cures.json absent, publish.py tourne hors "
            "du pipeline. Le signal en place est conserve tel quel."
        )

    ids_du_run = [entree["id"] for entree in nouveaux]
    entrees_du_run = [e for e in dans_fenetre if e.get("id") in set(ids_du_run)]
    signal = None

    if recolte_reelle:
        for entree in dans_fenetre:
            entree["signal"] = False
        signal = designer_signal(dans_fenetre, ids_du_run, aujourd_hui)
        if signal is not None:
            signal["signal"] = True
            # Marque definitive : un article a son tour en tete de page, une fois.
            signal["deja_signal"] = True

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

    if not recolte_reelle:
        # Rien a journaliser : le carnet decrit des executions du pipeline, et
        # celle-ci n'en est pas une.
        conserve = next((e["titre"] for e in dans_fenetre if e.get("signal")), None)
        print(f"Signal de la semaine : inchange ({conserve or 'aucun en place'}).")
        return

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
