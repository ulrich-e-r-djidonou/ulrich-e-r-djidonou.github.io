import contextlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

from pipeline import curate, publish


class SynchroniserSitemapTests(unittest.TestCase):
    # Reproduit la forme reellement publiee depuis la version anglaise : les
    # deux entrees de La Frontiere portent leurs annotations hreflang entre
    # <loc> et <lastmod>. Un sitemap sans xhtml:link laissait passer un motif
    # qui ne matchait plus rien en production.
    SITEMAP_BILINGUE = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <url>
    <loc>https://djidonou.com/</loc>
    <lastmod>2026-07-11</lastmod>
  </url>
  <url>
    <loc>https://djidonou.com/frontiere/</loc>
    <xhtml:link rel="alternate" hreflang="fr" href="https://djidonou.com/frontiere/"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://djidonou.com/en/frontier/"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="https://djidonou.com/frontiere/"/>
    <lastmod>2026-07-11</lastmod>
  </url>
  <url>
    <loc>https://djidonou.com/en/frontier/</loc>
    <xhtml:link rel="alternate" hreflang="fr" href="https://djidonou.com/frontiere/"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://djidonou.com/en/frontier/"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="https://djidonou.com/frontiere/"/>
    <lastmod>2026-07-11</lastmod>
  </url>
</urlset>
"""

    def _bac_a_sable(self, dossier):
        racine = Path(dossier)
        sitemap = racine / "sitemap.xml"
        meta = racine / "meta.json"
        sitemap.write_text(self.SITEMAP_BILINGUE, encoding="utf-8")
        meta.write_text(
            json.dumps({"derniere_mise_a_jour": "2026-07-30"}), encoding="utf-8"
        )
        return sitemap, meta

    def test_met_a_jour_uniquement_les_dates_de_la_frontiere(self):
        with tempfile.TemporaryDirectory() as dossier:
            sitemap, meta = self._bac_a_sable(dossier)

            publish.synchroniser_sitemap(sitemap, meta)

            resultat = sitemap.read_text(encoding="utf-8")
            self.assertIn(
                "<loc>https://djidonou.com/</loc>\n    <lastmod>2026-07-11</lastmod>",
                resultat,
            )
            self.assertEqual(resultat.count("<lastmod>2026-07-30</lastmod>"), 2)

    def test_met_a_jour_la_page_anglaise(self):
        # La page anglaise sert le meme flux : sa date doit suivre, sinon le
        # sitemap annonce une fraicheur fausse pour la moitie du site.
        with tempfile.TemporaryDirectory() as dossier:
            sitemap, meta = self._bac_a_sable(dossier)

            publish.synchroniser_sitemap(sitemap, meta)

            resultat = sitemap.read_text(encoding="utf-8")
            _, apres_entree_anglaise = resultat.split(
                "<loc>https://djidonou.com/en/frontier/</loc>", 1
            )
            self.assertIn("<lastmod>2026-07-30</lastmod>", apres_entree_anglaise)

    def test_echoue_si_une_des_deux_entrees_manque(self):
        with tempfile.TemporaryDirectory() as dossier:
            sitemap, meta = self._bac_a_sable(dossier)
            sitemap.write_text(
                self.SITEMAP_BILINGUE.replace(
                    "https://djidonou.com/en/frontier/</loc>",
                    "https://djidonou.com/en/frontiere/</loc>",
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                publish.synchroniser_sitemap(sitemap, meta)


class GenererJsonldFluxTests(unittest.TestCase):
    def test_distingue_la_redaction_du_travail_cite(self):
        entrees = [
            {
                "id": "arxiv-1",
                "titre": "Un papier externe",
                "url": "https://arxiv.org/abs/1",
                "source": "arXiv",
                "date_publication": "2026-08-01",
                "resume_fr": "Resume en francais.",
                "angle_eco": "Angle economique.",
                "themes": ["llm", "travail-emploi"],
                "auteurs": "A. Auteur, B. Auteur",
            }
        ]

        donnees = publish.generer_jsonld_flux(entrees)

        self.assertEqual(donnees["@type"], "ItemList")
        item = donnees["itemListElement"][0]["item"]
        self.assertEqual(item["author"], {"@id": "https://djidonou.com/#person"})
        self.assertIn("Resume en francais.", item["description"])
        self.assertIn("Angle economique.", item["description"])
        self.assertEqual(item["citation"]["url"], "https://arxiv.org/abs/1")
        self.assertEqual(item["citation"]["author"], "A. Auteur, B. Auteur")
        self.assertEqual(item["keywords"], "llm, travail-emploi")

    def test_retombe_sur_la_source_sans_auteurs(self):
        entrees = [{
            "id": "x", "titre": "T", "url": "https://x.example/1",
            "source": "VoxEU", "date_publication": "2026-08-01",
            "resume_fr": "R.", "angle_eco": "", "themes": [], "auteurs": "",
        }]

        donnees = publish.generer_jsonld_flux(entrees)

        self.assertEqual(
            donnees["itemListElement"][0]["item"]["citation"]["author"],
            "VoxEU",
        )

    def test_liste_vide_produit_un_itemlist_vide(self):
        donnees = publish.generer_jsonld_flux([])
        self.assertEqual(donnees["itemListElement"], [])


class InjecterJsonldFluxTests(unittest.TestCase):
    def test_remplace_le_bloc_flux_jsonld_sans_toucher_au_reste(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.html"
            index.write_text(
                """<html><head>
    <script type="application/ld+json">
    { "@type": "CollectionPage" }
    </script>

    <script type="application/ld+json" id="flux-jsonld">
    []
    </script>
</head></html>""",
                encoding="utf-8",
            )

            publish.injecter_jsonld_flux(
                {"@type": "ItemList", "itemListElement": [{"@type": "ListItem"}]},
                chemin_index=index,
            )

            resultat = index.read_text(encoding="utf-8")
            self.assertIn('"@type": "CollectionPage"', resultat)
            self.assertIn('"itemListElement"', resultat)
            bloc = resultat.split('id="flux-jsonld">', 1)[1].split("</script>", 1)[0]
            self.assertEqual(
                json.loads(bloc),
                {"@type": "ItemList", "itemListElement": [{"@type": "ListItem"}]},
            )

    def test_bloc_absent_leve_une_erreur(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.html"
            index.write_text("<html></html>", encoding="utf-8")

            with self.assertRaises(ValueError):
                publish.injecter_jsonld_flux({"@type": "ItemList"}, chemin_index=index)


class InventaireArchivesTests(unittest.TestCase):
    """Un mois d'archive vide existe comme fichier mais n'a rien a montrer.
    Le lister donnait un bouton menant a un ecran vide, ce qu'un visiteur
    lit comme une panne plutot que comme une absence de contenu."""

    def _dossier(self, contenus):
        dossier = Path(self.enveloppe.name)
        for mois, entrees in contenus.items():
            (dossier / f"{mois}.json").write_text(
                json.dumps(entrees, ensure_ascii=False), encoding="utf-8"
            )
        return dossier

    def setUp(self):
        self.enveloppe = tempfile.TemporaryDirectory()
        self.addCleanup(self.enveloppe.cleanup)

    def test_un_mois_vide_n_est_pas_liste(self):
        dossier = self._dossier({
            "2026-06": [],
            "2026-07": [{"id": "a"}, {"id": "b"}],
        })

        mois, comptes = publish.inventorier_archives(dossier)

        self.assertEqual(mois, ["2026-07"])
        self.assertNotIn("2026-06", comptes)

    def test_les_comptes_suivent_les_mois_listes(self):
        dossier = self._dossier({
            "2026-07": [{"id": "a"}, {"id": "b"}],
            "2026-08": [{"id": "c"}],
        })

        mois, comptes = publish.inventorier_archives(dossier)

        self.assertEqual(mois, ["2026-07", "2026-08"])
        self.assertEqual(comptes, {"2026-07": 2, "2026-08": 1})

    def test_aucune_archive_ne_leve_pas(self):
        mois, comptes = publish.inventorier_archives(Path(self.enveloppe.name))

        self.assertEqual(mois, [])
        self.assertEqual(comptes, {})


class EchappementBaliseScriptTests(unittest.TestCase):
    """Le titre d'un item vient brut du flux de la source. S'il contient
    </script>, le JSON-LD injecte dans frontiere/index.html fermerait la
    balise et le reste passerait pour du HTML executable, sur une page
    committee trois fois par semaine sans relecture humaine."""

    TITRE_PIEGE = "</script><img src=x onerror=alert(1)>"

    def test_un_titre_piege_ne_ferme_pas_la_balise(self):
        charge = publish.echapper_pour_balise_script(
            json.dumps({"headline": self.TITRE_PIEGE}, ensure_ascii=False)
        )

        self.assertNotIn("</script>", charge)
        self.assertNotIn("<", charge)

    def test_la_valeur_relue_est_identique_a_l_originale(self):
        """L'echappement doit etre transparent : un moteur de recherche ou un
        LLM qui relit le bloc doit voir exactement le titre d'origine."""
        charge = publish.echapper_pour_balise_script(
            json.dumps({"headline": self.TITRE_PIEGE}, ensure_ascii=False)
        )

        self.assertEqual(json.loads(charge)["headline"], self.TITRE_PIEGE)

    def test_le_bloc_injecte_dans_la_page_reste_clos(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.html"
            index.write_text(
                '<script type="application/ld+json" id="flux-jsonld">\n'
                "{}\n</script>",
                encoding="utf-8",
            )
            entrees = [{
                "titre": self.TITRE_PIEGE,
                "url": "https://example.test/a",
                "date_publication": "2026-08-01",
                "resume_fr": "resume",
                "source": "Source",
            }]

            publish.injecter_jsonld_flux(
                publish.generer_jsonld_flux(entrees), chemin_index=index
            )

            contenu = index.read_text(encoding="utf-8")
            # Une seule fermeture : celle de la balise ouverte plus haut.
            self.assertEqual(contenu.count("</script>"), 1)
            self.assertNotIn("<img", contenu)


class RepartirSelectionTests(unittest.TestCase):
    def test_separe_un_score_deux_d_un_score_trois(self):
        entrees = [
            {"id": "archive", "score": 2, "date_publication": "2026-08-01"},
            {"id": "selection", "score": 3, "date_publication": "2026-08-01"},
        ]

        selection, archives = publish.repartir_selection_et_archives(
            entrees,
            date(2026, 5, 3),
        )

        self.assertEqual([entree["id"] for entree in selection], ["selection"])
        self.assertEqual([entree["id"] for entree in archives], ["archive"])


class DesignerSignalTests(unittest.TestCase):
    """Dates construites par rapport a REFERENCE, jamais litterales.

    designer_signal raisonne sur une fenetre glissante de 7 jours : une date
    figee dans le code finirait par en sortir et ferait echouer ces tests un
    mois plus tard, sur un commit sans rapport (voir
    pipeline/verifier_dates_tests.py).
    """

    REFERENCE = date(2026, 8, 17)

    def entree(self, identifiant, score, jours_avant):
        return {
            "id": identifiant,
            "titre": identifiant,
            "score": score,
            "date_publication": (
                self.REFERENCE - timedelta(days=jours_avant)
            ).isoformat(),
        }

    def test_ecarte_un_ancien_hors_semaine_meme_mieux_note(self):
        # Defaut d'origine : un article bien note gardait la place jusqu'a
        # sortir des 90 jours. Hors des 7 jours, il ne concourt plus tant que
        # la semaine a quelque chose a proposer.
        hors_semaine = self.entree("hors-semaine", 9, publish.FENETRE_SIGNAL_JOURS + 3)
        frais = self.entree("frais", 6, 0)

        signal = publish.designer_signal(
            [hors_semaine, frais],
            ["frais"],
            self.REFERENCE,
        )

        self.assertEqual(signal["id"], "frais")

    def test_le_meilleur_de_la_semaine_gagne_meme_hors_du_run(self):
        # Le vivier est la semaine, pas l'execution : un article de la semaine
        # jamais passe en signal reste candidat, meme si le run ne l'a pas
        # rapporte cette fois-ci.
        du_run = self.entree("du-run", 6, 0)
        de_la_semaine = self.entree("de-la-semaine", 9, 3)

        signal = publish.designer_signal(
            [du_run, de_la_semaine],
            ["du-run"],
            self.REFERENCE,
        )

        self.assertEqual(signal["id"], "de-la-semaine")

    def test_aucun_signal_si_le_vivier_frais_reste_sous_le_plancher(self):
        ancien = dict(self.entree("ancien", 9, 7), deja_signal=True)
        frais = self.entree("frais", publish.SEUIL_SIGNAL - 1, 0)

        signal = publish.designer_signal(
            [ancien, frais],
            ["frais"],
            self.REFERENCE,
        )

        self.assertIsNone(signal)

    def test_la_semaine_reste_candidate_quand_le_run_est_maigre(self):
        # Motif du 17 aout 2026 : une execution manuelle n'ayant rapporte que
        # des items faibles effacait un signal valide, alors que la semaine en
        # contenait de bons. Une recolte maigre n'est pas une semaine vide.
        faible = self.entree("faible", publish.SEUIL_SIGNAL - 2, 0)
        bon_de_la_semaine = self.entree("bon", publish.SEUIL_SIGNAL, 2)

        signal = publish.designer_signal(
            [faible, bon_de_la_semaine],
            ["faible"],
            self.REFERENCE,
        )

        self.assertEqual(signal["id"], "bon")

    def test_un_article_deja_passe_en_signal_est_ecarte(self):
        # Coeur de la demande initiale : ne plus revoir le meme article d'une
        # semaine sur l'autre. La fenetre glissante seule ne suffit pas, un
        # article restant eligible tant qu'il n'en est pas sorti.
        ancien_signal = dict(self.entree("ancien", 9, 3), deja_signal=True)
        neuf = self.entree("neuf", publish.SEUIL_SIGNAL, 0)

        signal = publish.designer_signal(
            [ancien_signal, neuf],
            ["neuf"],
            self.REFERENCE,
        )

        self.assertEqual(signal["id"], "neuf")

    def test_replie_hors_semaine_quand_le_vivier_frais_est_vide(self):
        vieux = self.entree("vieux", 9, publish.FENETRE_SIGNAL_JOURS + 5)

        signal = publish.designer_signal([vieux], [], self.REFERENCE)

        self.assertEqual(signal["id"], "vieux")

    def test_aucun_signal_si_tous_sont_deja_passes(self):
        epuises = [
            dict(self.entree(f"vu-{i}", 9, i), deja_signal=True) for i in range(3)
        ]

        self.assertIsNone(publish.designer_signal(epuises, [], self.REFERENCE))

    def test_flux_vide_ne_designe_rien(self):
        self.assertIsNone(publish.designer_signal([], [], self.REFERENCE))

    def test_a_score_egal_le_plus_economique_passe_devant(self):
        # Un 6 vaut 2 x 3 ou 3 x 2 : le score seul ne les distingue pas.
        peu_eco = dict(self.entree("peu-eco", 6, 0), nb_eco=2, nb_ia=3)
        tres_eco = dict(self.entree("tres-eco", 6, 0), nb_eco=3, nb_ia=2)

        signal = publish.designer_signal(
            [peu_eco, tres_eco],
            ["peu-eco", "tres-eco"],
            self.REFERENCE,
        )

        self.assertEqual(signal["id"], "tres-eco")

    def test_a_poids_egal_le_titre_economique_tranche(self):
        neutre = dict(
            self.entree("neutre", 6, 0), nb_eco=3, titre="A Survey of Large Models",
        )
        economique = dict(
            self.entree("economique", 6, 0),
            nb_eco=3,
            titre="Labor market effects of automation on wages",
        )

        signal = publish.designer_signal(
            [neutre, economique],
            ["neutre", "economique"],
            self.REFERENCE,
        )

        self.assertEqual(signal["id"], "economique")

    def test_la_date_ne_departage_qu_en_dernier(self):
        recent_neutre = dict(
            self.entree("recent", 6, 0), nb_eco=1, titre="A Survey of Large Models",
        )
        ancien_economique = dict(
            self.entree("ancien", 6, 3), nb_eco=4, titre="Wages and productivity",
        )

        signal = publish.designer_signal(
            [recent_neutre, ancien_economique],
            ["recent", "ancien"],
            self.REFERENCE,
        )

        self.assertEqual(signal["id"], "ancien")

    def test_une_entree_sans_nb_eco_est_departagee_sur_son_titre(self):
        # Les entrees publiees avant le 17 aout 2026 ne portent pas nb_eco,
        # l'abstract sur lequel il se calcule n'etant pas verse dans le flux.
        ancienne = self.entree("ancienne", 6, 0)
        ancienne["titre"] = "Wages, growth and inequality under automation"
        autre = self.entree("autre", 6, 0)
        autre["titre"] = "A Survey of Large Models"

        signal = publish.designer_signal(
            [autre, ancienne],
            ["autre", "ancienne"],
            self.REFERENCE,
        )

        self.assertEqual(signal["id"], "ancienne")


class PoidsEconomiqueTitreTests(unittest.TestCase):
    def test_compte_les_mots_cles_economiques_du_titre(self):
        self.assertEqual(
            publish.poids_economique_titre("Wages and labor market policy"), 4,
        )

    def test_un_titre_sans_vocabulaire_economique_vaut_zero(self):
        self.assertEqual(
            publish.poids_economique_titre("A Survey of Large Models in Sports"), 0,
        )

    def test_titre_absent_ne_leve_pas(self):
        self.assertEqual(publish.poids_economique_titre(None), 0)

    def test_utilise_la_liste_de_curate_sans_copie(self):
        # Deux listes qui derivent l'une de l'autre feraient departager le
        # signal sur un vocabulaire different de celui qui l'a rendu eligible.
        mot = curate.MOTS_CLES_ECO[0]
        self.assertGreaterEqual(publish.poids_economique_titre(mot), 1)


class CompleterDerniereExecutionTests(unittest.TestCase):
    """Dates litterales assumees : ce sont des cles d'appariement, pas des
    bornes de fenetre glissante. La fonction compare une date a une autre,
    sans notion d'anciennete."""

    JOUR = date(2026, 8, 17)

    def ligne(self, jour):
        return {"date": jour.isoformat(), "nb_publies": 3}

    def test_complete_la_ligne_du_jour_sans_en_ajouter(self):
        historique = [self.ligne(self.JOUR - timedelta(days=4)), self.ligne(self.JOUR)]

        resultat, complete = publish.completer_derniere_execution(
            historique, self.JOUR, True, 8,
        )

        self.assertTrue(complete)
        self.assertEqual(len(resultat), 2)
        self.assertTrue(resultat[-1]["signal_designe"])
        self.assertEqual(resultat[-1]["score_max"], 8)
        self.assertNotIn("signal_designe", resultat[0])

    def test_ne_cree_rien_si_la_ligne_du_jour_manque(self):
        # publish.py lance seul, hors du workflow : curate.py n'a pas ecrit de
        # ligne, et en inventer une fausserait le compte d'executions.
        historique = [self.ligne(self.JOUR - timedelta(days=4))]

        resultat, complete = publish.completer_derniere_execution(
            historique, self.JOUR, False, 4,
        )

        self.assertFalse(complete)
        self.assertEqual(len(resultat), 1)
        self.assertNotIn("signal_designe", resultat[0])

    def test_historique_vide_ne_declenche_rien(self):
        resultat, complete = publish.completer_derniere_execution(
            [], self.JOUR, True, 9,
        )
        self.assertFalse(complete)
        self.assertEqual(resultat, [])

    def test_absence_de_signal_est_enregistree_comme_telle(self):
        historique = [self.ligne(self.JOUR)]

        resultat, _ = publish.completer_derniere_execution(
            historique, self.JOUR, False, 4,
        )

        self.assertIs(resultat[-1]["signal_designe"], False)
        self.assertEqual(resultat[-1]["score_max"], 4)

    def test_recolte_vide_journalise_none_et_non_zero(self):
        # 0 se confondrait avec une recolte dont tous les scores seraient nuls.
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "sante.json"
            chemin.write_text(
                json.dumps([self.ligne(self.JOUR)]), encoding="utf-8",
            )

            publish.enregistrer_issue_signal(None, [], self.JOUR, chemin)

            ligne = json.loads(chemin.read_text(encoding="utf-8"))[-1]
            self.assertIsNone(ligne["score_max"])
            self.assertIs(ligne["signal_designe"], False)

    def test_carnet_illisible_ne_leve_pas(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "sante.json"
            chemin.write_text("{ pas du json", encoding="utf-8")

            publish.enregistrer_issue_signal(None, [], self.JOUR, chemin)

            self.assertEqual(chemin.read_text(encoding="utf-8"), "{ pas du json")


class MainTests(unittest.TestCase):
    """Chaine complete de publish.main() dans un bac a sable.

    Seul maillon que les tests de fonctions pures ne couvraient pas : la
    lecture de _candidats_cures.json, donc la construction de ids_du_run, dont
    depend le premier palier du signal. Une regression y serait passee
    inapercue jusqu'a la prochaine execution planifiee.

    Les dates sont relatives a date.today() : main() lit l'horloge, et une
    date figee finirait par sortir de la fenetre de 90 jours.
    """

    INDEX_MINIMAL = (
        '<html><body><script type="application/ld+json" id="flux-jsonld">'
        "\n{}\n</script></body></html>"
    )
    SITEMAP_MINIMAL = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        "  <url>\n    <loc>https://djidonou.com/frontiere/</loc>\n"
        '    <xhtml:link rel="alternate" hreflang="en"'
        ' href="https://djidonou.com/en/frontier/"/>\n'
        "    <lastmod>2020-01-01</lastmod>\n  </url>\n"
        "  <url>\n    <loc>https://djidonou.com/en/frontier/</loc>\n"
        '    <xhtml:link rel="alternate" hreflang="fr"'
        ' href="https://djidonou.com/frontiere/"/>\n'
        "    <lastmod>2020-01-01</lastmod>\n  </url>\n</urlset>\n"
    )

    def entree(self, identifiant, score, jours_avant, **extra):
        aujourd_hui = date.today()
        entree = {
            "id": identifiant,
            "titre": identifiant,
            "url": f"https://exemple.test/{identifiant}",
            "source": "arXiv",
            "type": "papier",
            "date_publication": (
                aujourd_hui - timedelta(days=jours_avant)
            ).isoformat(),
            "resume_fr": "Resume.",
            "angle_eco": "Angle.",
            "themes": ["llm"],
            "score": score,
            "auteurs": "Untel",
            "signal": False,
        }
        entree.update(extra)
        return entree

    def bac_a_sable(self, pile, cures, flux_existant):
        """Monte un faux depot et branche les chemins du module dessus."""
        racine = Path(pile.enter_context(tempfile.TemporaryDirectory()))
        donnees = racine / "frontiere" / "data"
        donnees.mkdir(parents=True)
        (racine / "frontiere" / "index.html").write_text(
            self.INDEX_MINIMAL, encoding="utf-8",
        )
        (racine / "sitemap.xml").write_text(self.SITEMAP_MINIMAL, encoding="utf-8")
        (donnees / "flux.json").write_text(
            json.dumps(flux_existant, ensure_ascii=False), encoding="utf-8",
        )
        cures_chemin = racine / "_candidats_cures.json"
        cures_chemin.write_text(json.dumps(cures, ensure_ascii=False), encoding="utf-8")

        for nom, valeur in {
            "RACINE": racine,
            "DONNEES": donnees,
            "ARCHIVES": donnees / "archives",
            "CURES": cures_chemin,
            "CANDIDATS_ARCHIVES": racine / "_candidats_archives.json",
            "SITEMAP": racine / "sitemap.xml",
            "FRONTIERE_INDEX": racine / "frontiere" / "index.html",
        }.items():
            pile.enter_context(mock.patch.object(publish, nom, valeur))
        return racine, donnees

    def test_le_signal_vient_des_candidats_cures_du_run(self):
        # L'ancien, mieux note, est deja dans le flux mais a eu son tour ; le
        # frais arrive par _candidats_cures.json, seul fichier a prouver ici.
        ancien = self.entree("ancien", 9, 5, deja_signal=True)
        frais = self.entree("frais", 6, 0, nb_eco=3, nb_ia=2)

        with contextlib.ExitStack() as pile:
            _, donnees = self.bac_a_sable(pile, [frais], [ancien])
            publish.main()

            flux = json.loads((donnees / "flux.json").read_text(encoding="utf-8"))

        signaux = [e["id"] for e in flux if e.get("signal")]
        self.assertEqual(signaux, ["frais"])
        self.assertEqual(len(flux), 2)

    def test_le_plancher_laisse_le_flux_sans_signal(self):
        frais = self.entree("frais", publish.SEUIL_SIGNAL - 1, 0)
        ancien = self.entree("ancien", 9, 5, deja_signal=True)

        with contextlib.ExitStack() as pile:
            _, donnees = self.bac_a_sable(pile, [frais], [ancien])
            publish.main()

            flux = json.loads((donnees / "flux.json").read_text(encoding="utf-8"))

        self.assertEqual([e["id"] for e in flux if e.get("signal")], [])

    def test_ecrit_meta_feed_et_jsonld_sans_toucher_au_vrai_depot(self):
        frais = self.entree("frais", 6, 0, nb_eco=3, nb_ia=2)

        with contextlib.ExitStack() as pile:
            racine, donnees = self.bac_a_sable(pile, [frais], [])
            publish.main()

            meta = json.loads((donnees / "meta.json").read_text(encoding="utf-8"))
            feed = (racine / "frontiere" / "feed.xml").read_text(encoding="utf-8")
            index = (racine / "frontiere" / "index.html").read_text(encoding="utf-8")
            sitemap = (racine / "sitemap.xml").read_text(encoding="utf-8")

        self.assertEqual(meta["nb_entrees_flux"], 1)
        self.assertEqual(meta["derniere_mise_a_jour"], date.today().isoformat())
        self.assertIn("frais", feed)
        self.assertIn("frais", index)
        self.assertIn(f"<lastmod>{date.today().isoformat()}</lastmod>", sitemap)

    def test_deja_signal_survit_a_une_nouvelle_redaction(self):
        # regenerer_flux.py reecrit des entrees deja publiees. Sans report du
        # marqueur, un article deja passe en tete de page y reviendrait.
        deja_vu = self.entree("deja-vu", 9, 2, deja_signal=True)
        rediger_a_nouveau = self.entree("deja-vu", 9, 2, resume_fr="Nouveau texte.")
        autre = self.entree("autre", publish.SEUIL_SIGNAL, 1)

        with contextlib.ExitStack() as pile:
            _, donnees = self.bac_a_sable(
                pile, [rediger_a_nouveau, autre], [deja_vu],
            )
            publish.main()

            flux = json.loads((donnees / "flux.json").read_text(encoding="utf-8"))

        par_id = {e["id"]: e for e in flux}
        self.assertTrue(par_id["deja-vu"]["deja_signal"])
        self.assertEqual(par_id["deja-vu"]["resume_fr"], "Nouveau texte.")
        self.assertEqual([e["id"] for e in flux if e.get("signal")], ["autre"])

    def test_sans_fichier_de_candidats_le_signal_en_place_est_conserve(self):
        # publish.py lance seul, hors du pipeline : ce n'est pas une recolte
        # vide, c'est l'absence de recolte. Redesigner detruirait le signal en
        # place, ce qui est arrive deux fois le 17 aout 2026.
        en_place = self.entree("en-place", 6, 4, signal=True, deja_signal=True)
        concurrent = self.entree("concurrent", 9, 1)

        with contextlib.ExitStack() as pile:
            racine, donnees = self.bac_a_sable(
                pile, [], [en_place, concurrent],
            )
            (racine / "_candidats_cures.json").unlink()
            publish.main()

            flux = json.loads((donnees / "flux.json").read_text(encoding="utf-8"))

        self.assertEqual([e["id"] for e in flux if e.get("signal")], ["en-place"])

    def test_sans_fichier_de_candidats_la_maintenance_se_poursuit(self):
        # La fenetre, les archives et le sitemap restent tenus : le garde-fou
        # protege le signal, il ne gele pas le reste.
        recent = self.entree("recent", 6, 1, signal=True, deja_signal=True)
        perime = self.entree("perime", 6, publish.FENETRE_JOURS + 5)

        with contextlib.ExitStack() as pile:
            racine, donnees = self.bac_a_sable(pile, [], [recent, perime])
            (racine / "_candidats_cures.json").unlink()
            publish.main()

            flux = json.loads((donnees / "flux.json").read_text(encoding="utf-8"))
            archives = sorted((donnees / "archives").glob("*.json"))

        self.assertEqual([e["id"] for e in flux], ["recent"])
        self.assertEqual(len(archives), 1)

    def test_un_flux_existant_ne_devient_jamais_vide(self):
        # Garde-fou deja present dans main() : sans candidat et avec un flux
        # entierement hors fenetre, la page garde son etat plutot que de se
        # vider.
        perime = self.entree("perime", 6, publish.FENETRE_JOURS + 10)

        with contextlib.ExitStack() as pile:
            _, donnees = self.bac_a_sable(pile, [], [perime])
            publish.main()

            flux = json.loads((donnees / "flux.json").read_text(encoding="utf-8"))

        self.assertEqual([e["id"] for e in flux], ["perime"])


if __name__ == "__main__":
    unittest.main()
