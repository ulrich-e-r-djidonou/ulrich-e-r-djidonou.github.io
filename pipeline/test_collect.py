import json
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import yaml

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


class SeparerAuteursAvantDoubleBrTests(unittest.TestCase):
    def test_extrait_les_auteurs_et_le_reste_du_resume(self):
        auteurs, reste = collect.separer_auteurs_avant_double_br(
            '<a href="https://x.invalid">Alice Martin</a>, Bob Roy'
            "<br /><br />Le resume commence ici."
        )
        self.assertEqual(auteurs, "Alice Martin, Bob Roy")
        self.assertEqual(reste, "Le resume commence ici.")

    def test_variante_sans_espace_entre_les_deux_br(self):
        auteurs, reste = collect.separer_auteurs_avant_double_br(
            "Alice Martin<br/><br/>Resume."
        )
        self.assertEqual(auteurs, "Alice Martin")
        self.assertEqual(reste, "Resume.")

    def test_motif_absent_renvoie_auteurs_vide_et_le_resume_entier(self):
        auteurs, reste = collect.separer_auteurs_avant_double_br("Un resume sans auteurs.")
        self.assertEqual(auteurs, "")
        self.assertEqual(reste, "Un resume sans auteurs.")


class AuteursNatifsFeedparserTests(unittest.TestCase):
    def test_champ_authors_prefere_au_champ_author(self):
        entree = {"author": "ignore", "authors": [{"name": "Alice Martin, Bob Roy"}]}
        self.assertEqual(collect.auteurs_natifs_feedparser(entree), "Alice Martin, Bob Roy")

    def test_repli_sur_le_champ_author_si_authors_absent(self):
        entree = {"author": "Alice Martin"}
        self.assertEqual(collect.auteurs_natifs_feedparser(entree), "Alice Martin")

    def test_aucun_champ_auteur_renvoie_chaine_vide(self):
        self.assertEqual(collect.auteurs_natifs_feedparser({}), "")


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
    def _reponse(self, contenu=b""):
        return SimpleNamespace(content=contenu, raise_for_status=lambda: None)

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
        with patch.object(collect.requests, "get", return_value=self._reponse()), \
             patch.object(collect.feedparser, "parse", return_value=flux_simule):
            resultat = collect.collecter_rss(source)
        self.assertEqual(len(resultat), 1)
        self.assertEqual(resultat[0]["titre"], "Self-Fulfilling Credit Scores")
        self.assertEqual(resultat[0]["auteurs"], "Victor Duarte, Julia Fonseca")
        self.assertEqual(resultat[0]["type"], "papier")
        self.assertIsNotNone(resultat[0]["date_publication"])

    def test_auteurs_avant_double_br_extraits_du_resume(self):
        """Cas reel du flux de la Fed : la liste d'auteurs precede le
        resume, separee par « </a><br /><br /> », sans aucun espace autour.
        Avec auteurs_avant_double_br, le segment doit devenir le champ
        auteurs, pas rester colle au debut de l'abstract (regression du
        2026-08-11 : 1 item sur 45 sans auteur affiche dans La Frontiere)."""
        source = {
            "id": "fed",
            "nom": "Fed",
            "url": "https://example.invalid/rss.xml",
            "auteurs_avant_double_br": True,
        }
        flux_simule = SimpleNamespace(
            bozo=False,
            entries=[
                {
                    "title": "Un papier",
                    "summary": (
                        '<a href="https://example.invalid/a">Alice Martin</a>, Bob Roy'
                        "<br /><br />Despite documented heterogeneity..."
                    ),
                    "link": "https://example.invalid/papier",
                }
            ],
        )
        with patch.object(collect.requests, "get", return_value=self._reponse()), \
             patch.object(collect.feedparser, "parse", return_value=flux_simule):
            resultat = collect.collecter_rss(source)
        self.assertEqual(resultat[0]["auteurs"], "Alice Martin, Bob Roy")
        self.assertEqual(resultat[0]["abstract"], "Despite documented heterogeneity...")

    def test_sans_auteurs_avant_double_br_le_resume_reste_entier(self):
        """Sans le drapeau active pour la source, le comportement d'avant
        est preserve : aucune balise ne colle deux mots ensemble."""
        source = {"id": "bce", "nom": "BCE", "url": "https://example.invalid/rss.xml"}
        flux_simule = SimpleNamespace(
            bozo=False,
            entries=[
                {
                    "title": "Un papier",
                    "summary": (
                        '<a href="https://example.invalid/a">Alice Martin</a>'
                        "<br /><br />Despite documented heterogeneity..."
                    ),
                    "link": "https://example.invalid/papier",
                }
            ],
        )
        with patch.object(collect.requests, "get", return_value=self._reponse()), \
             patch.object(collect.feedparser, "parse", return_value=flux_simule):
            resultat = collect.collecter_rss(source)
        self.assertEqual(resultat[0]["auteurs"], "")
        self.assertEqual(
            resultat[0]["abstract"], "Alice Martin Despite documented heterogeneity..."
        )

    def test_auteurs_natifs_feedparser_utilises_a_defaut_dautre_source(self):
        """Cas reel de VoxEU/CEPR : ni separateur dans le titre, ni double
        saut de ligne dans le resume, mais feedparser expose deja les
        auteurs (balise <author> ou <dc:creator> du flux d'origine)."""
        source = {"id": "voxeu", "nom": "VoxEU / CEPR", "url": "https://example.invalid/rss.xml"}
        flux_simule = SimpleNamespace(
            bozo=False,
            entries=[
                {
                    "title": "Un article",
                    "summary": "Ce papier etudie...",
                    "link": "https://example.invalid/article",
                    "author": "Alessandro Caiumi, Giovanni Peri",
                    "authors": [{"name": "Alessandro Caiumi, Giovanni Peri"}],
                }
            ],
        )
        with patch.object(collect.requests, "get", return_value=self._reponse()), \
             patch.object(collect.feedparser, "parse", return_value=flux_simule):
            resultat = collect.collecter_rss(source)
        self.assertEqual(resultat[0]["auteurs"], "Alessandro Caiumi, Giovanni Peri")

    def test_recupere_le_contenu_via_requests_plutot_que_feedparser(self):
        """feedparser ne doit plus aller chercher l'URL lui-meme : son propre
        magasin de certificats TLS depend de la plateforme (voir le flux de
        la BCE, qui echoue via urllib mais reussit via requests)."""
        source = {"id": "bce", "nom": "BCE", "url": "https://example.invalid/rss.xml"}
        flux_simule = SimpleNamespace(bozo=False, entries=[])
        with patch.object(collect.requests, "get", return_value=self._reponse(b"<rss></rss>")) as get_simule, \
             patch.object(collect.feedparser, "parse", return_value=flux_simule) as parse_simule:
            collect.collecter_rss(source)
        get_simule.assert_called_once_with(
            source["url"], timeout=collect.TIMEOUT, headers=collect.NAVIGATEUR
        )
        parse_simule.assert_called_once_with(b"<rss></rss>")

    def test_erreur_http_propage_une_exception(self):
        """Une source RSS en panne doit lever, pour que main() la loggue en
        echec sans bloquer les autres sources."""
        source = {"id": "bce", "nom": "BCE", "url": "https://example.invalid/rss.xml"}
        reponse_en_echec = SimpleNamespace(
            content=b"",
            raise_for_status=lambda: (_ for _ in ()).throw(RuntimeError("500")),
        )
        with patch.object(collect.requests, "get", return_value=reponse_en_echec):
            with self.assertRaises(RuntimeError):
                collect.collecter_rss(source)


class EtiquetteTypeItemTests(unittest.TestCase):
    """« Papier » et « Article » doivent refleter le statut de publication du
    document, jamais le protocole de collecte.

    Chaque collecteur applique un defaut different (« article » pour le RSS,
    « papier » pour Crossref). Le 2026-08-12, cela affichait les working
    papers de la Fed et de la BCE comme des articles publies, et les revues
    a comite de lecture de l'AEA comme des papiers de travail. Ces tests
    figent la convention decrite en tete de sources.yaml."""

    ATTENDU = {
        "arxiv-econ": "papier",
        "arxiv-ml-econ": "papier",
        "nber": "papier",
        "fmi": "papier",
        "ssrn": "papier",
        "fed": "papier",
        "bce": "papier",
        "aea": "article",
        "voxeu": "article",
    }

    def setUp(self):
        config = yaml.safe_load(collect.SOURCES_YAML.read_text(encoding="utf-8"))
        self.sources = {s["id"]: s for s in config["sources"]}

    def test_chaque_source_porte_l_etiquette_attendue(self):
        for identifiant, attendu in self.ATTENDU.items():
            with self.subTest(source=identifiant):
                self.assertEqual(self.sources[identifiant].get("type_item"), attendu)

    def test_l_etiquette_est_explicite_et_non_heritee_du_collecteur(self):
        """Un type_item absent laisserait le defaut du collecteur decider,
        c'est-a-dire le protocole plutot que la nature du document."""
        for identifiant in self.ATTENDU:
            with self.subTest(source=identifiant):
                self.assertIn("type_item", self.sources[identifiant])

    def test_seules_les_etiquettes_connues_sont_utilisees(self):
        """Une valeur hors de cette liste ne serait traduite par aucun libelle
        dans NOMS_TYPES (frontiere.js) et s'afficherait brute au lecteur."""
        connues = {"papier", "article", "outil", "dataset", "annonce", "cours"}
        for identifiant, source in self.sources.items():
            if "type_item" in source:
                with self.subTest(source=identifiant):
                    self.assertIn(source["type_item"], connues)


class LienPubliableTests(unittest.TestCase):
    """Le lien d'un item vient du flux de la source. Publie tel quel dans un
    href, un schema `javascript:` s'executerait au clic du visiteur."""

    def test_accepte_http_et_https(self):
        self.assertTrue(collect.lien_publiable("https://www.nber.org/papers/w1"))
        self.assertTrue(collect.lien_publiable("http://arxiv.org/abs/2501.00001"))

    def test_rejette_les_schemas_executables(self):
        for url in (
            "javascript:alert(1)",
            "JavaScript:alert(1)",
            "  javascript:alert(1)  ",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
        ):
            with self.subTest(url=url):
                self.assertFalse(collect.lien_publiable(url))

    def test_rejette_le_vide(self):
        """Remplace l'ancien `if not lien` : un item sans lien reste ecarte."""
        self.assertFalse(collect.lien_publiable(""))
        self.assertFalse(collect.lien_publiable(None))


if __name__ == "__main__":
    unittest.main()
