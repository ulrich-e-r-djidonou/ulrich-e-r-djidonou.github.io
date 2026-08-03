import json
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from pipeline import collect


class MotCleSousChaineTests(unittest.TestCase):
    """« llm » comme sous-chaine attrape « enrollment » : voir collect.py."""

    def test_llm_isole_est_detecte(self):
        self.assertTrue(collect.mot_cle_present("new llm agents", "llm"))

    def test_llm_en_debut_de_mot_compose_est_detecte(self):
        self.assertTrue(collect.mot_cle_present("llm-based pipeline", "llm"))

    def test_enrollment_ne_declenche_pas_llm(self):
        self.assertFalse(collect.mot_cle_present("school enrollment effects", "llm"))

    def test_racine_econom_reste_en_sous_chaine(self):
        self.assertTrue(collect.mot_cle_present("macroeconomics of trade", "econom"))

    def test_contient_mot_cle_ia_sur_enrollment_seul(self):
        self.assertFalse(
            collect.contient_mot_cle(
                "College enrollment and wage growth", collect.MOTS_CLES_IA
            )
        )

    def test_contient_mot_cle_ia_sur_gpt(self):
        self.assertTrue(
            collect.contient_mot_cle(
                "ChatGPT adoption in firms", collect.MOTS_CLES_IA
            )
        )


class SeparerTitreAuteursTests(unittest.TestCase):
    def test_separe_titre_et_auteurs_nber(self):
        titre, auteurs = collect.separer_titre_auteurs(
            "Self-Fulfilling Credit Scores -- by Victor Duarte, Julia Fonseca",
            " -- by ",
        )
        self.assertEqual(titre, "Self-Fulfilling Credit Scores")
        self.assertEqual(auteurs, "Victor Duarte, Julia Fonseca")

    def test_sans_separateur_configure_renvoie_le_titre_entier(self):
        titre, auteurs = collect.separer_titre_auteurs("Un titre simple", None)
        self.assertEqual(titre, "Un titre simple")
        self.assertEqual(auteurs, "")

    def test_separateur_absent_du_titre_renvoie_le_titre_entier(self):
        titre, auteurs = collect.separer_titre_auteurs(
            "Un titre sans le motif", " -- by "
        )
        self.assertEqual(titre, "Un titre sans le motif")
        self.assertEqual(auteurs, "")


class NettoyerAbstractJatsTests(unittest.TestCase):
    def test_retire_le_titre_abstract_et_les_balises(self):
        brut = "<jats:title>Abstract</jats:title><jats:p>Le texte &amp; la suite.</jats:p>"
        self.assertEqual(collect.nettoyer_abstract_jats(brut), "Le texte & la suite.")

    def test_texte_vide_renvoie_chaine_vide(self):
        self.assertEqual(collect.nettoyer_abstract_jats(""), "")
        self.assertEqual(collect.nettoyer_abstract_jats(None), "")


class DateCrossrefTests(unittest.TestCase):
    def test_date_complete_est_retenue(self):
        item = {"published": {"date-parts": [[2026, 7, 15]]}}
        self.assertEqual(collect.date_crossref(item), date(2026, 7, 15))

    def test_date_reduite_a_lannee_est_ignoree_au_profit_du_champ_suivant(self):
        item = {
            "published": {"date-parts": [[2026]]},
            "created": {"date-parts": [[2026, 3, 2]]},
        }
        self.assertEqual(collect.date_crossref(item), date(2026, 3, 2))

    def test_aucune_date_exploitable_renvoie_none(self):
        item = {"published": {"date-parts": [[2026]]}}
        self.assertIsNone(collect.date_crossref(item))

    def test_date_annee_mois_seuls_retombe_au_premier_du_mois(self):
        item = {"published": {"date-parts": [[2026, 7]]}}
        self.assertEqual(collect.date_crossref(item), date(2026, 7, 1))


class CollecterCrossrefTests(unittest.TestCase):
    def _reponse(self, items):
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"message": {"items": items}},
        )

    def test_filtre_les_items_sans_abstract(self):
        source = {
            "id": "aea",
            "nom": "AEA",
            "issn": ["0002-8282"],
            "axe_date": "publication",
            "requiert_mot_cle_ia": True,
            "fenetre_jours": 60,
        }
        items_crossref = [
            {
                "DOI": "10.1257/aer.1",
                "title": ["Machine learning in labor markets"],
                "abstract": "<jats:p>Une etude sur le machine learning et le marche du travail.</jats:p>",
                "published": {"date-parts": [[2026, 7, 1]]},
                "author": [{"given": "A", "family": "B"}],
                "container-title": ["American Economic Review"],
            },
            {
                "DOI": "10.1257/aer.2",
                "title": ["Sans resume"],
                "abstract": "",
                "published": {"date-parts": [[2026, 7, 1]]},
            },
        ]
        with patch.object(collect.requests, "get", return_value=self._reponse(items_crossref)):
            resultat = collect.collecter_crossref(source)
        self.assertEqual(len(resultat), 1)
        self.assertEqual(resultat[0]["id"], "aea-10-1257-aer-1")
        self.assertEqual(resultat[0]["auteurs"], "A B")
        self.assertEqual(resultat[0]["source"], "American Economic Review")

    def test_filtre_mot_cle_ia_ecarte_les_items_hors_sujet(self):
        source = {
            "id": "aea",
            "nom": "AEA",
            "issn": ["0002-8282"],
            "axe_date": "publication",
            "requiert_mot_cle_ia": True,
            "fenetre_jours": 60,
        }
        items_crossref = [
            {
                "DOI": "10.1257/aer.3",
                "title": ["School enrollment and local labor markets"],
                "abstract": "<jats:p>Effets de la scolarisation sur le marche du travail local.</jats:p>",
                "published": {"date-parts": [[2026, 7, 1]]},
            },
        ]
        with patch.object(collect.requests, "get", return_value=self._reponse(items_crossref)):
            resultat = collect.collecter_crossref(source)
        self.assertEqual(resultat, [])

    def test_axe_depot_utilise_created_pour_la_date(self):
        source = {
            "id": "ssrn",
            "nom": "SSRN",
            "prefixe_doi": "10.2139",
            "axe_date": "depot",
            "requiert_mot_cle_eco": True,
            "requiert_mot_cle_ia": True,
            "fenetre_jours": 14,
        }
        items_crossref = [
            {
                "DOI": "10.2139/ssrn.1",
                "title": ["Artificial intelligence and wage inequality"],
                "abstract": "<jats:p>IA, salaires et inegalite du marche du travail.</jats:p>",
                "published": {"date-parts": [[2026]]},
                "created": {"date-parts": [[2026, 7, 30]]},
            },
        ]
        with patch.object(collect.requests, "get", return_value=self._reponse(items_crossref)):
            resultat = collect.collecter_crossref(source)
        self.assertEqual(len(resultat), 1)
        self.assertEqual(resultat[0]["date_publication"], "2026-07-30")


class CollecterRssNberTests(unittest.TestCase):
    def test_titre_et_auteurs_separes_avec_date_de_repli(self):
        source = {
            "id": "nber",
            "nom": "NBER",
            "url": "https://example.invalid/rss.xml",
            "separateur_auteurs": " -- by ",
            "date_repli": "collecte",
            "type_item": "papier",
            "fenetre_jours": 30,
        }
        flux_simule = SimpleNamespace(
            bozo=False,
            entries=[
                {
                    "title": "Self-Fulfilling Credit Scores -- by Victor Duarte, Julia Fonseca",
                    "summary": "Un resume sans date fournie par le flux.",
                    "link": "https://www.nber.org/papers/w35508",
                }
            ],
        )
        with patch.object(collect.feedparser, "parse", return_value=flux_simule):
            resultat = collect.collecter_rss(source)
        self.assertEqual(len(resultat), 1)
        self.assertEqual(resultat[0]["titre"], "Self-Fulfilling Credit Scores")
        self.assertEqual(resultat[0]["auteurs"], "Victor Duarte, Julia Fonseca")
        self.assertEqual(resultat[0]["type"], "papier")
        self.assertIsNotNone(resultat[0]["date_publication"])


if __name__ == "__main__":
    unittest.main()
