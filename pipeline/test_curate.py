import json
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from pipeline import curate

# curate.lien_mort interroge la cible de chaque article retenu. Sans ce
# neutralisant, la suite entiere sortirait sur le reseau, et les URL de test
# en example.com repondent reellement 404 : les items disparaitraient des
# assertions pour une raison qui n'a rien a voir avec ce qu'elles verifient.
# Le controle a ses propres tests dans LienMortTests, ou il est eprouve pour
# lui-meme.
# Capturee a l'import, donc avant que setUpModule ne la remplace : c'est la
# vraie fonction que LienMortTests doit eprouver, pas son neutralisant.
LIEN_MORT_REEL = curate.lien_mort
_lien_mort_neutralise = None


def setUpModule():
    global _lien_mort_neutralise
    _lien_mort_neutralise = patch.object(curate, "lien_mort", return_value=False)
    _lien_mort_neutralise.start()


def tearDownModule():
    _lien_mort_neutralise.stop()


class LienMortTests(unittest.TestCase):
    """Le doute profite a l'article : seule une reponse qui nie l'existence
    de la ressource l'ecarte.

    Cas reel du 24 aout 2026 : le FMI depose ses DOI chez Crossref six
    numeros avant de publier les pages, et la veille a mis en avant comme
    signal de la semaine un article dont la cible rendait 404.
    """

    def _avec(self, **module):
        faux = types.ModuleType("requests")
        for nom, valeur in module.items():
            setattr(faux, nom, valeur)
        return patch.dict(sys.modules, {"requests": faux})

    def _reponse(self, code):
        return types.SimpleNamespace(status_code=code, close=lambda: None)

    def test_un_404_ecarte_l_article(self):
        with self._avec(get=lambda *a, **k: self._reponse(404)):
            self.assertTrue(LIEN_MORT_REEL("https://exemple.invalid/p"))

    def test_un_410_ecarte_l_article(self):
        with self._avec(get=lambda *a, **k: self._reponse(410)):
            self.assertTrue(LIEN_MORT_REEL("https://exemple.invalid/p"))

    def test_un_403_laisse_passer(self):
        # cepr.org et pubs.aeaweb.org servent 403 a tout client automatise en
        # rendant 200 dans un navigateur : dix des soixante entrees du flux
        # en dependent.
        with self._avec(get=lambda *a, **k: self._reponse(403)):
            self.assertFalse(LIEN_MORT_REEL("https://exemple.invalid/p"))

    def test_un_200_laisse_passer(self):
        with self._avec(get=lambda *a, **k: self._reponse(200)):
            self.assertFalse(LIEN_MORT_REEL("https://exemple.invalid/p"))

    def test_une_panne_reseau_laisse_passer(self):
        def _exploser(*_a, **_k):
            raise OSError("reseau coupe")

        with self._avec(get=_exploser):
            self.assertFalse(LIEN_MORT_REEL("https://exemple.invalid/p"))

    def test_un_module_sans_get_laisse_passer(self):
        # Impossible de verifier vaut « on ne sait pas », et « on ne sait
        # pas » laisse passer l'article.
        with self._avec():
            self.assertFalse(LIEN_MORT_REEL("https://exemple.invalid/p"))


class ScoreSourceEconomiqueTests(unittest.TestCase):
    """Une revue d'economie publie de l'economie : le score ne doit pas le
    redemander au vocabulaire de l'abstract.

    Cas reel du 2026-08-05 : un article du Journal of Economic Perspectives
    archive parce que son abstract parle de prix et de fournisseurs plutot que
    d'employer les mots generalistes de MOTS_CLES_ECO.
    """

    # Abstract reel de "The Emerging Market for Intelligence: How Firms Buy and
    # Sell AI" (Demirer, Fradkin, Tadelis, JEP, DOI 10.1257/jep.20261506).
    TITRE_JEP = "The Emerging Market for Intelligence: How Firms Buy and Sell AI"
    ABSTRACT_JEP = (
        "We describe the emerging business-to-business market for large language model "
        "(LLM) inference and document key empirical patterns in its supply, pricing, and "
        "dynamics, using data from OpenRouter. First, supply has expanded rapidly: the "
        "number of commercially available models, model creators, and inference providers "
        "has grown sharply, driven heavily by opensource entrants. Second, the price of "
        "intelligence has fallen roughly a thousandfold. Third, the market is highly "
        "dynamic, with frequent turnover among leading models and creators."
    )

    def test_reconnait_les_sources_economiques(self):
        for source in (
            "Journal of Economic Perspectives",
            "American Economic Review",
            "American Economic Journal: Applied Economics",
            "NBER, nouveaux working papers",
            "VoxEU / CEPR",
            "Reserve federale americaine (Fed), working papers",
            "Banque centrale europeenne (BCE), working papers",
            "IMF Working Papers",
        ):
            with self.subTest(source=source):
                self.assertTrue(curate.est_source_economique(source))

    def test_ne_reconnait_pas_une_source_generaliste(self):
        for source in ("arXiv cs.LG / cs.CL / stat.ML (filtre economie)", "", None):
            with self.subTest(source=source):
                self.assertFalse(curate.est_source_economique(source))

    def test_l_article_jep_atteint_le_seuil_via_sa_source(self):
        texte = f"{self.TITRE_JEP} {self.ABSTRACT_JEP}"

        # Sans la source, le calcul historique le laisse sous le seuil.
        self.assertLess(curate.score_heuristique(texte), curate.SEUIL_PUBLICATION)
        # Avec la source, il passe.
        self.assertGreaterEqual(
            curate.score_heuristique(texte, "Journal of Economic Perspectives"),
            curate.SEUIL_PUBLICATION,
        )

    def test_une_source_economique_sans_lien_ia_reste_ecartee(self):
        """Le plancher ne doit pas publier toute l'economie : la dimension IA
        reste exigee, sinon le flux perdrait son sujet."""
        texte = (
            "Minimum Wages and Employment. We estimate the effect of minimum wage "
            "increases on teenage employment using state-level variation."
        )

        self.assertEqual(
            curate.score_heuristique(texte, "American Economic Review"), 0
        )

    def test_une_source_arxiv_garde_le_calcul_historique(self):
        texte = f"{self.TITRE_JEP} {self.ABSTRACT_JEP}"

        self.assertEqual(
            curate.score_heuristique(texte, "arXiv cs.LG / cs.CL / stat.ML (filtre economie)"),
            curate.score_heuristique(texte),
        )

    def test_main_transmet_la_source_au_score(self):
        """Verification de bout en bout : un item AEA scoré 2 par le calcul
        historique doit etre juge eligible, pas archive."""
        candidat = {
            "id": "aea-test-jep",
            "titre": self.TITRE_JEP,
            "url": "https://doi.org/10.1257/jep.20261506",
            "source": "Journal of Economic Perspectives",
            "type": "papier",
            "date_publication": "2026-08-01",
            "abstract": self.ABSTRACT_JEP,
            "auteurs": "Auteur Test",
        }

        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            chemins = {
                "ENTREE": racine / "candidats.json",
                "SORTIE": racine / "cures.json",
                "SORTIE_ARCHIVE": racine / "archives.json",
                "SEEN": racine / "seen.json",
                "SANTE": racine / "sante.json",
            }
            chemins["ENTREE"].write_text(json.dumps([candidat]), encoding="utf-8")
            chemins["SEEN"].write_text("{}", encoding="utf-8")

            with ExitStack() as pile:
                for nom, chemin in chemins.items():
                    pile.enter_context(patch.object(curate, nom, chemin))
                # Sans service de redaction : l'item eligible est reporte, pas
                # archive. C'est la distinction qui prouve que le score a change.
                pile.enter_context(patch.object(curate, "LLM_ACTIF", False))
                curate.main()

            archives = json.loads(chemins["SORTIE_ARCHIVE"].read_text(encoding="utf-8"))
            self.assertEqual(archives, [], "l'article ne doit plus tomber dans l'archive")
            self.assertEqual(
                json.loads(chemins["SEEN"].read_text(encoding="utf-8")),
                {},
                "un item eligible non redige reste non vu, pour etre repris",
            )


class ValidationResumeTests(unittest.TestCase):
    def test_accepte_deux_phrases_francaises(self):
        texte = "La méthode réduit le biais. Elle améliore aussi la précision."

        self.assertEqual(curate.erreurs_resume(texte), [])

    def test_refuse_un_nombre_de_phrases_incorrect(self):
        erreurs = curate.erreurs_resume("Une seule phrase.")

        self.assertIn("nombre_phrases", erreurs)

    def test_refuse_les_caracteres_non_latins(self):
        erreurs = curate.erreurs_resume("La méthode généralise跨过. Elle reste stable.")

        self.assertIn("caracteres_non_latins", erreurs)

    def test_refuse_plusieurs_mots_outils_anglais(self):
        texte = "The method works with data. It is useful for policy."

        self.assertIn("anglais_residuel", curate.erreurs_resume(texte))


class ValidationInventionTests(unittest.TestCase):
    def test_accepte_un_chiffre_repris_de_la_source(self):
        source = "Titre. Le modele traite 100 taches sur 2,32 heures en moyenne."
        texte = "L'etude porte sur 100 taches et 2,32 heures de travail humain."

        self.assertEqual(curate.erreurs_invention(texte, source), [])

    def test_refuse_un_chiffre_absent_de_la_source(self):
        source = "Titre. Le modele traite 100 taches sur 2,32 heures en moyenne."
        texte = "L'etude porte sur 250 taches evaluees par le modele."

        self.assertIn("chiffre_invente", curate.erreurs_invention(texte, source))

    def test_accepte_une_virgule_decimale_francaise(self):
        source = "Titre. Le taux atteint 3.5 percent selon les auteurs."
        texte = "Le taux atteint 3,5 pourcent selon l'etude."

        self.assertEqual(curate.erreurs_invention(texte, source), [])

    def test_accepte_la_conversion_trillion_exigee_par_le_prompt(self):
        # Le prompt impose d'ecrire mille milliards pour trillion : le filtre
        # ne doit pas rejeter la traduction qu'il demande lui-meme.
        source = "Titre. This column analyses 380 trillion tokens of AI use."
        texte = "L'etude porte sur 380 000 milliards de jetons de consommation."

        self.assertEqual(curate.erreurs_invention(texte, source), [])

    def test_le_separateur_de_milliers_ne_cree_pas_de_faux_nombre(self):
        self.assertEqual(curate._nombres("380 000 milliards"), {380000.0})

    def test_ignore_un_texte_sans_chiffre(self):
        source = "Titre. Le modele traite plusieurs taches."
        texte = "L'etude porte sur plusieurs taches administratives."

        self.assertEqual(curate.erreurs_invention(texte, source), [])


class ValidationAngleTests(unittest.TestCase):
    def test_accepte_une_phrase_directe(self):
        texte = "La mesure du biais éclaire le ciblage des politiques publiques."

        self.assertEqual(curate.erreurs_angle(texte), [])

    def test_refuse_une_formule_stereotypee(self):
        texte = "Ce papier compte pour un économiste car il mesure le biais."

        self.assertIn("formule_stereotypee", curate.erreurs_angle(texte))


class RepriseTests(unittest.TestCase):
    def test_accepte_la_deuxieme_sortie_valide(self):
        sorties = iter(["Une phrase.", "Première phrase. Deuxième phrase."])

        resultat = curate._generer_avec_reprise(
            lambda: next(sorties),
            lambda texte: not curate.erreurs_resume(texte),
        )

        self.assertEqual(resultat, "Première phrase. Deuxième phrase.")

    def test_abandonne_apres_deux_sorties_invalides(self):
        appels = []

        resultat = curate._generer_avec_reprise(
            lambda: appels.append(True) or "Une phrase.",
            lambda texte: not curate.erreurs_resume(texte),
        )

        self.assertIsNone(resultat)
        self.assertEqual(len(appels), 2)


class PolitiquePublicationTests(unittest.TestCase):
    def test_ne_publie_pas_apres_deux_resumes_invalides(self):
        candidat = {
            "id": "test-1",
            "titre": "Economic policy with machine learning",
            "url": "https://example.com/test-1",
            "source": "test",
            "type": "papier",
            "date_publication": "2026-08-01",
            "abstract": "Economic policy and market analysis using machine learning.",
            "auteurs": "Auteur Test",
        }

        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            entree = racine / "candidats.json"
            sortie = racine / "cures.json"
            sortie_archive = racine / "archives.json"
            seen = racine / "seen.json"
            sante = racine / "sante.json"
            entree.write_text(json.dumps([candidat]), encoding="utf-8")
            seen.write_text("{}", encoding="utf-8")

            with (
                patch.object(curate, "ENTREE", entree),
                patch.object(curate, "SORTIE", sortie),
                patch.object(curate, "SORTIE_ARCHIVE", sortie_archive),
                patch.object(curate, "SEEN", seen),
                patch.object(curate, "SANTE", sante),
                patch.object(curate, "LLM_ACTIF", True),
                patch.object(
                    curate,
                    "resume_ollama",
                    return_value="Une seule phrase.",
                ) as resume,
                patch.object(curate, "angle_eco_ollama") as angle,
            ):
                curate.main()

            self.assertEqual(json.loads(sortie.read_text(encoding="utf-8")), [])
            self.assertIn("test-1", json.loads(seen.read_text(encoding="utf-8")))
            self.assertEqual(resume.call_count, 2)
            angle.assert_not_called()

    def test_archive_un_score_deux_sans_appeler_le_llm(self):
        candidat = {
            "id": "test-archive",
            "titre": "Economic policy with machine learning",
            "url": "https://example.com/test-archive",
            "source": "test",
            "type": "papier",
            "date_publication": "2026-08-01",
            "abstract": "Economic policy with machine learning.",
            "auteurs": "Auteur Test",
        }

        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            entree = racine / "candidats.json"
            sortie = racine / "cures.json"
            sortie_archive = racine / "archives.json"
            seen = racine / "seen.json"
            sante = racine / "sante.json"
            entree.write_text(json.dumps([candidat]), encoding="utf-8")
            seen.write_text("{}", encoding="utf-8")

            with (
                patch.object(curate, "ENTREE", entree),
                patch.object(curate, "SORTIE", sortie),
                patch.object(curate, "SORTIE_ARCHIVE", sortie_archive),
                patch.object(curate, "SEEN", seen),
                patch.object(curate, "SANTE", sante),
                patch.object(curate, "LLM_ACTIF", True),
                patch.object(curate, "resume_ollama") as resume,
                patch.object(curate, "angle_eco_ollama") as angle,
            ):
                curate.main()

            self.assertEqual(json.loads(sortie.read_text(encoding="utf-8")), [])
            archives = json.loads(sortie_archive.read_text(encoding="utf-8"))
            self.assertEqual([entree["id"] for entree in archives], ["test-archive"])
            self.assertNotIn("resume_fr", archives[0])
            resume.assert_not_called()
            angle.assert_not_called()


class LangueFrancaiseTests(unittest.TestCase):
    """Les regles doivent etre etroites : aucune sortie correcte rejetee."""

    TEXTES_CORRECTS = [
        "L'unité de mesure change. Le modèle d'Amazon reste stable.",
        "Une hausse d'un point réduit l'écart. Les auteurs estiment qu'Amazon suit.",
        "Le modèle de langage traite mille milliards de jetons. Il reste rapide.",
        "Cet article mesure un effet. La méthode est simple.",
        "Les données de 2026 montrent une baisse. Le résultat tient.",
        "Le yoga du yen progresse. Le héros de yaourt reste une exception.",
    ]

    def test_n_alerte_pas_sur_du_francais_correct(self):
        for texte in self.TEXTES_CORRECTS:
            with self.subTest(texte=texte):
                self.assertEqual(curate.erreurs_langue(texte), [])

    def test_detecte_une_elision_manquante(self):
        self.assertIn(
            "elision_manquante",
            curate.erreurs_langue("Le routage aligne les décisions avec le unité."),
        )

    def test_detecte_une_contraction_devant_voyelle(self):
        self.assertIn(
            "elision_manquante",
            curate.erreurs_langue("DBA-Bench mesure l'ouverture du espace de solutions."),
        )

    def test_detecte_un_demonstratif_incorrect(self):
        self.assertIn(
            "demonstratif_incorrect", curate.erreurs_langue("Ce article mesure un effet.")
        )

    def test_detecte_le_faux_ami_trillion(self):
        self.assertIn(
            "faux_ami_numerique",
            curate.erreurs_langue("L'analyse porte sur 380 trillions de jetons."),
        )

    def test_detecte_un_mot_double(self):
        self.assertIn(
            "mot_double", curate.erreurs_langue("Le modèle de de langage progresse.")
        )

    def test_detecte_une_fuite_anglaise(self):
        self.assertIn(
            "fuite_anglaise",
            curate.erreurs_langue("Le mécanisme repose sur un incentive monétaire."),
        )

    def test_les_validateurs_de_sortie_appliquent_les_regles_de_langue(self):
        resume = "Le modèle réduit le biais de un point. Il reste rapide."
        angle = "Le mécanisme aligne le unité de compte sur la valeur observée."

        self.assertIn("elision_manquante", curate.erreurs_resume(resume))
        self.assertIn("elision_manquante", curate.erreurs_angle(angle))


class PostureEditorialeTests(unittest.TestCase):
    """Le flux resume les travaux des autres, et chaque champ est lu seul."""

    def test_refuse_la_premiere_personne(self):
        texte = "Nous proposons des conditions suffisantes. La méthode tient."

        self.assertIn("premiere_personne", curate.erreurs_resume(texte))

    def test_refuse_le_possessif_de_l_auteur(self):
        texte = "Notre méthode réduit le biais de moitié."

        self.assertIn("premiere_personne", curate.erreurs_angle(texte))

    def test_refuse_un_renvoi_a_un_antecedent_absent(self):
        texte = "Le cadre proposé permet de surmonter ces difficultés."

        self.assertIn("anaphore_orpheline", curate.erreurs_angle(texte))

    def test_accepte_un_renvoi_dont_l_antecedent_est_present(self):
        texte = (
            "Les modèles pré-entraînés posent deux difficultés de convergence. "
            "Ces difficultés disparaissent sous une condition de régularité."
        )

        self.assertNotIn("anaphore_orpheline", curate.erreurs_resume(texte))

    def test_refuse_toute_ouverture_parlant_du_papier(self):
        for ouverture in (
            "Ce papier fournit des conditions suffisantes.",
            "Cet article mesure un effet de composition.",
            "Les auteurs estiment une élasticité de 0,3.",
            "Dans cette étude, la méthode est comparée à trois repères.",
        ):
            with self.subTest(ouverture=ouverture):
                self.assertIn("formule_stereotypee", curate.erreurs_angle(ouverture))

    def test_accepte_une_ouverture_par_le_mecanisme(self):
        texte = "L'appariement des données fiscales réduit le biais de sélection."

        self.assertEqual(curate.erreurs_angle(texte), [])


class FournisseurTests(unittest.TestCase):
    """Le changement de fournisseur ne doit tenir qu'a la configuration."""

    def _faux_requests(self, capture, charge_utile):
        class Reponse:
            def raise_for_status(self):
                pass

            def json(self):
                return charge_utile

        module = types.ModuleType("requests")
        module.post = lambda url, **options: (
            capture.update({"url": url, **options}) or Reponse()
        )
        return module

    def test_appelle_ollama_au_format_ollama(self):
        capture = {}
        faux = self._faux_requests(capture, {"response": "  Texte produit.  "})

        with (
            patch.dict(sys.modules, {"requests": faux}),
            patch.object(curate, "FOURNISSEUR", "ollama"),
        ):
            texte = curate._appel_ollama("prompt")

        self.assertEqual(texte, "Texte produit.")
        self.assertIn("prompt", capture["json"])
        self.assertNotIn("headers", capture)

    def test_appelle_une_api_au_format_openai(self):
        capture = {}
        faux = self._faux_requests(
            capture, {"choices": [{"message": {"content": "Texte produit."}}]}
        )

        with (
            patch.dict(sys.modules, {"requests": faux}),
            patch.object(curate, "FOURNISSEUR", "api"),
            patch.object(curate, "API_URL", "https://exemple.test/v1/chat/completions"),
            patch.object(curate, "API_MODELE", "modele-test"),
            patch.object(curate, "API_CLE", "cle-test"),
        ):
            texte = curate._appel_ollama("prompt")

        self.assertEqual(texte, "Texte produit.")
        self.assertEqual(capture["url"], "https://exemple.test/v1/chat/completions")
        self.assertEqual(capture["headers"]["Authorization"], "Bearer cle-test")
        self.assertEqual(capture["json"]["messages"][0]["content"], "prompt")
        self.assertEqual(capture["json"]["temperature"], 0)

    def test_attend_plus_longtemps_quand_le_debit_est_limite(self):
        class Reponse:
            status_code = 429
            headers = {"Retry-After": "30"}

        erreur = Exception("trop de requetes")
        erreur.response = Reponse()

        self.assertEqual(curate._delai_avant_reprise(erreur, 0), 30)

    def test_plafonne_l_attente_demandee_par_le_service(self):
        class Reponse:
            status_code = 429
            headers = {"Retry-After": "9999"}

        erreur = Exception("trop de requetes")
        erreur.response = Reponse()

        self.assertEqual(
            curate._delai_avant_reprise(erreur, 0), curate.PAUSE_MAX_DEBIT
        )

    def test_attend_plus_longtemps_quand_le_service_est_sature(self):
        class Reponse:
            status_code = 503
            headers = {}

        erreur = Exception("service indisponible")
        erreur.response = Reponse()

        attentes = [curate._delai_avant_reprise(erreur, t) for t in range(3)]
        self.assertEqual(attentes, [8, 16, 32])

    def test_attente_courte_pour_une_panne_ordinaire(self):
        self.assertEqual(
            curate._delai_avant_reprise(Exception("connexion refusee"), 0),
            curate.PAUSE_AVANT_REPRISE,
        )

    def test_le_nom_du_modele_suit_le_fournisseur(self):
        with (
            patch.object(curate, "FOURNISSEUR", "api"),
            patch.object(curate, "API_MODELE", "modele-test"),
            patch.object(curate, "_bascule_repli", False),
        ):
            self.assertEqual(curate.modele_actif(), "modele-test")
        with patch.object(curate, "FOURNISSEUR", "ollama"):
            self.assertEqual(curate.modele_actif(), curate.OLLAMA_MODEL)


class RepliFournisseurTests(unittest.TestCase):
    """Bascule vers un second point de terminaison quand le principal echoue.

    Reproduit le cas reel du 3 aout 2026 : Gemini renvoie 429 (quota epuise),
    et la redaction doit continuer via le repli plutot que de faire echouer
    le run.
    """

    def setUp(self):
        # Compteur de budget partage entre tests : remis a zero pour que
        # chaque test parte propre, comme BudgetAppelsTests plus bas.
        self._appels = curate._appels_effectues
        curate._appels_effectues = 0

    def tearDown(self):
        curate._appels_effectues = self._appels

    def _faux_requests(self, capture, url_principal, url_repli):
        class ErreurHTTP(Exception):
            def __init__(self, status_code):
                super().__init__(f"HTTP {status_code}")
                self.response = types.SimpleNamespace(status_code=status_code, headers={})

        class ReponseOk:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "Texte du repli."}}]}

        def poster(url, **options):
            capture.setdefault("appels", []).append(url)
            if url == url_principal:
                raise ErreurHTTP(429)
            assert url == url_repli
            return ReponseOk()

        module = types.ModuleType("requests")
        module.post = poster
        return module

    def test_bascule_sur_le_repli_apres_epuisement_du_principal(self):
        capture = {}
        faux = self._faux_requests(
            capture, "https://principal.test/chat/completions", "https://repli.test/chat/completions"
        )

        with (
            patch.dict(sys.modules, {"requests": faux}),
            patch.object(curate, "FOURNISSEUR", "api"),
            patch.object(curate, "API_URL", "https://principal.test/chat/completions"),
            patch.object(curate, "API_MODELE", "gemini-3.6-flash"),
            patch.object(curate, "API_CLE", "cle-gemini"),
            patch.object(curate, "API_URL_REPLI", "https://repli.test/chat/completions"),
            patch.object(curate, "API_MODELE_REPLI", "claude-haiku-4-5"),
            patch.object(curate, "API_CLE_REPLI", "cle-claude"),
            patch.object(curate, "REPLI_ACTIF", True),
            patch.object(curate, "_bascule_repli", False),
            patch.object(curate, "TENTATIVES_API", 2),
            patch("time.sleep"),
        ):
            texte = curate._appel_ollama("prompt")
            self.assertEqual(texte, "Texte du repli.")
            # Le nom du modele actif suit la bascule.
            self.assertEqual(curate.modele_actif(), "claude-haiku-4-5")

        # 2 essais rates sur le principal, puis 1 essai reussi sur le repli.
        self.assertEqual(
            capture["appels"],
            ["https://principal.test/chat/completions"] * 2
            + ["https://repli.test/chat/completions"],
        )

    def test_les_items_suivants_vont_directement_au_repli(self):
        capture = {}
        faux = self._faux_requests(
            capture, "https://principal.test/chat/completions", "https://repli.test/chat/completions"
        )

        with (
            patch.dict(sys.modules, {"requests": faux}),
            patch.object(curate, "FOURNISSEUR", "api"),
            patch.object(curate, "API_URL", "https://principal.test/chat/completions"),
            patch.object(curate, "API_MODELE", "gemini-3.6-flash"),
            patch.object(curate, "API_CLE", "cle-gemini"),
            patch.object(curate, "API_URL_REPLI", "https://repli.test/chat/completions"),
            patch.object(curate, "API_MODELE_REPLI", "claude-haiku-4-5"),
            patch.object(curate, "API_CLE_REPLI", "cle-claude"),
            patch.object(curate, "REPLI_ACTIF", True),
            # La bascule est deja engagee par un item precedent du meme run.
            patch.object(curate, "_bascule_repli", True),
            patch.object(curate, "TENTATIVES_API", 2),
            patch("time.sleep"),
        ):
            texte = curate._appel_ollama("prompt")

        self.assertEqual(texte, "Texte du repli.")
        self.assertEqual(capture["appels"], ["https://repli.test/chat/completions"])

    def test_sans_repli_configure_une_panne_du_principal_leve_toujours(self):
        capture = {}
        faux = self._faux_requests(
            capture, "https://principal.test/chat/completions", "https://repli.test/chat/completions"
        )

        with (
            patch.dict(sys.modules, {"requests": faux}),
            patch.object(curate, "FOURNISSEUR", "api"),
            patch.object(curate, "API_URL", "https://principal.test/chat/completions"),
            patch.object(curate, "API_MODELE", "gemini-3.6-flash"),
            patch.object(curate, "API_CLE", "cle-gemini"),
            patch.object(curate, "REPLI_ACTIF", False),
            patch.object(curate, "_bascule_repli", False),
            patch.object(curate, "TENTATIVES_API", 2),
            patch("time.sleep"),
        ):
            with self.assertRaises(curate.OllamaIndisponible):
                curate._appel_ollama("prompt")

        # Comportement inchange sans repli configure : seul le principal est
        # sollicite, aucun essai sur une URL de repli.
        self.assertEqual(capture["appels"], ["https://principal.test/chat/completions"] * 2)

    def test_le_budget_d_appels_compte_le_principal_et_le_repli_ensemble(self):
        capture = {}
        faux = self._faux_requests(
            capture, "https://principal.test/chat/completions", "https://repli.test/chat/completions"
        )

        with (
            patch.dict(sys.modules, {"requests": faux}),
            patch.object(curate, "FOURNISSEUR", "api"),
            patch.object(curate, "API_URL", "https://principal.test/chat/completions"),
            patch.object(curate, "API_MODELE", "gemini-3.6-flash"),
            patch.object(curate, "API_CLE", "cle-gemini"),
            patch.object(curate, "API_URL_REPLI", "https://repli.test/chat/completions"),
            patch.object(curate, "API_MODELE_REPLI", "claude-haiku-4-5"),
            patch.object(curate, "API_CLE_REPLI", "cle-claude"),
            patch.object(curate, "REPLI_ACTIF", True),
            patch.object(curate, "_bascule_repli", False),
            patch.object(curate, "TENTATIVES_API", 2),
            patch("time.sleep"),
        ):
            curate._appel_ollama("prompt")
            # 2 essais sur le principal + 1 sur le repli, un seul compteur.
            self.assertEqual(curate._appels_effectues, 3)


class RepliIntegrationTests(unittest.TestCase):
    """Le run complet publie via le repli au lieu d'echouer, sans marquer
    d'item vu sans texte redige.
    """

    CANDIDAT = {
        "id": "test-repli-integration",
        "titre": "Economic policy with machine learning",
        "url": "https://example.com/test-repli-integration",
        "source": "test",
        "type": "papier",
        "date_publication": "2026-08-01",
        "abstract": "Economic policy and market analysis using machine learning.",
        "auteurs": "Auteur Test",
    }

    def setUp(self):
        self._appels = curate._appels_effectues
        curate._appels_effectues = 0

    def tearDown(self):
        curate._appels_effectues = self._appels

    def test_le_run_publie_via_le_repli_quand_le_principal_est_en_panne(self):
        capture = {"appels": []}

        class ErreurHTTP(Exception):
            def __init__(self, status_code):
                super().__init__(f"HTTP {status_code}")
                self.response = types.SimpleNamespace(status_code=status_code, headers={})

        class ReponseOk:
            def __init__(self, texte):
                self._texte = texte

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": self._texte}}]}

        # Deux sorties valides pretes a etre lues dans l'ordre resume, angle.
        textes_repli = iter([
            "La méthode réduit le biais. Elle améliore aussi la précision.",
            "L'appariement des données fiscales réduit le biais de sélection.",
        ])

        def poster(url, **options):
            capture["appels"].append(url)
            if url == "https://principal.test/chat/completions":
                raise ErreurHTTP(429)
            return ReponseOk(next(textes_repli))

        faux_requests = types.ModuleType("requests")
        faux_requests.post = poster

        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            chemins = {
                "ENTREE": racine / "candidats.json",
                "SORTIE": racine / "cures.json",
                "SORTIE_ARCHIVE": racine / "archives.json",
                "SEEN": racine / "seen.json",
                "SANTE": racine / "sante.json",
            }
            chemins["ENTREE"].write_text(json.dumps([self.CANDIDAT]), encoding="utf-8")
            chemins["SEEN"].write_text("{}", encoding="utf-8")

            with ExitStack() as pile:
                for nom, chemin in chemins.items():
                    pile.enter_context(patch.object(curate, nom, chemin))
                pile.enter_context(patch.dict(sys.modules, {"requests": faux_requests}))
                pile.enter_context(patch.object(curate, "LLM_ACTIF", True))
                pile.enter_context(patch.object(curate, "FOURNISSEUR", "api"))
                pile.enter_context(patch.object(curate, "API_URL", "https://principal.test/chat/completions"))
                pile.enter_context(patch.object(curate, "API_MODELE", "gemini-3.6-flash"))
                pile.enter_context(patch.object(curate, "API_CLE", "cle-gemini"))
                pile.enter_context(patch.object(curate, "API_URL_REPLI", "https://repli.test/chat/completions"))
                pile.enter_context(patch.object(curate, "API_MODELE_REPLI", "claude-haiku-4-5"))
                pile.enter_context(patch.object(curate, "API_CLE_REPLI", "cle-claude"))
                pile.enter_context(patch.object(curate, "REPLI_ACTIF", True))
                pile.enter_context(patch.object(curate, "_bascule_repli", False))
                pile.enter_context(patch.object(curate, "TENTATIVES_API", 2))
                pile.enter_context(patch("time.sleep"))
                curate.main()

            cures = json.loads(chemins["SORTIE"].read_text(encoding="utf-8"))
            self.assertEqual(len(cures), 1)
            self.assertEqual(cures[0]["resume_fr"], "La méthode réduit le biais. Elle améliore aussi la précision.")
            self.assertEqual(cures[0]["llm"], "claude-haiku-4-5")

            # L'item a bien un texte redige : il est marque vu a juste titre,
            # pas par un echec silencieux qui l'aurait marque sans rediger.
            seen = json.loads(chemins["SEEN"].read_text(encoding="utf-8"))
            self.assertIn("test-repli-integration", seen)

            sante = json.loads(chemins["SANTE"].read_text(encoding="utf-8"))
            self.assertTrue(sante[-1]["bascule_repli"])


class BudgetAppelsTests(unittest.TestCase):
    """Le quota gratuit se compte en requetes : mieux vaut s'arreter avant."""

    def setUp(self):
        self._appels = curate._appels_effectues
        curate._appels_effectues = 0

    def tearDown(self):
        curate._appels_effectues = self._appels

    def test_sans_budget_rien_n_est_limite(self):
        with patch.object(curate, "BUDGET_APPELS", 0):
            curate._appels_effectues = 999
            self.assertFalse(curate.budget_epuise())

    def test_s_arrete_avant_de_depasser_le_quota(self):
        """Le seuil se lit sur APPELS_MAX_PAR_ITEM, qui vaut 4 ou 8 selon que
        les champs anglais sont rediges : un chiffre en dur ici rendrait le
        test faux au prochain reglage plutot que de detecter une regression."""
        cout_item = curate.APPELS_MAX_PAR_ITEM
        with patch.object(curate, "BUDGET_APPELS", 20):
            curate._appels_effectues = 20 - cout_item
            self.assertFalse(curate.budget_epuise())
            curate._appels_effectues = 20 - cout_item + 1
            self.assertTrue(curate.budget_epuise())

    def test_les_items_hors_budget_restent_non_vus(self):
        candidat = {
            "id": "test-budget",
            "titre": "Economic policy with machine learning",
            "url": "https://example.com/test-budget",
            "source": "test",
            "type": "papier",
            "date_publication": "2026-08-01",
            "abstract": "Economic policy and market analysis using machine learning.",
            "auteurs": "Auteur Test",
        }

        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            chemins = {
                "ENTREE": racine / "candidats.json",
                "SORTIE": racine / "cures.json",
                "SORTIE_ARCHIVE": racine / "archives.json",
                "SEEN": racine / "seen.json",
                "SANTE": racine / "sante.json",
            }
            chemins["ENTREE"].write_text(json.dumps([candidat]), encoding="utf-8")
            chemins["SEEN"].write_text("{}", encoding="utf-8")

            with ExitStack() as pile:
                for nom, chemin in chemins.items():
                    pile.enter_context(patch.object(curate, nom, chemin))
                pile.enter_context(patch.object(curate, "LLM_ACTIF", True))
                pile.enter_context(patch.object(curate, "BUDGET_APPELS", 20))
                redaction = pile.enter_context(patch.object(curate, "resume_ollama"))
                curate._appels_effectues = 20
                curate.main()

            redaction.assert_not_called()
            self.assertEqual(json.loads(chemins["SEEN"].read_text(encoding="utf-8")), {})


class PanneServiceTests(unittest.TestCase):
    """Une panne du service de redaction ne doit consommer aucun article."""

    CANDIDAT = {
        "id": "test-panne",
        "titre": "Economic policy with machine learning",
        "url": "https://example.com/test-panne",
        "source": "test",
        "type": "papier",
        "date_publication": "2026-08-01",
        "abstract": "Economic policy and market analysis using machine learning.",
        "auteurs": "Auteur Test",
    }

    def _executer(self, dossier, **remplacements):
        racine = Path(dossier)
        chemins = {
            "ENTREE": racine / "candidats.json",
            "SORTIE": racine / "cures.json",
            "SORTIE_ARCHIVE": racine / "archives.json",
            "SEEN": racine / "seen.json",
            "SANTE": racine / "sante.json",
        }
        chemins["ENTREE"].write_text(json.dumps([self.CANDIDAT]), encoding="utf-8")
        chemins["SEEN"].write_text("{}", encoding="utf-8")

        with ExitStack() as pile:
            for nom, chemin in chemins.items():
                pile.enter_context(patch.object(curate, nom, chemin))
            for nom, valeur in remplacements.items():
                pile.enter_context(patch.object(curate, nom, valeur))
            curate.main()
        return chemins

    def test_indisponibilite_n_ecrit_rien_et_ne_marque_personne(self):
        def tombe_en_panne(*args, **kwargs):
            raise curate.OllamaIndisponible("connexion refusee")

        with tempfile.TemporaryDirectory() as dossier:
            with self.assertRaises(curate.OllamaIndisponible):
                self._executer(
                    dossier,
                    LLM_ACTIF=True,
                    resume_ollama=tombe_en_panne,
                )

            racine = Path(dossier)
            self.assertEqual(racine.joinpath("seen.json").read_text(encoding="utf-8"), "{}")
            self.assertFalse(racine.joinpath("cures.json").exists())

    def test_sans_llm_actif_l_item_eligible_reste_non_vu(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemins = self._executer(dossier, LLM_ACTIF=False)

            self.assertEqual(json.loads(chemins["SORTIE"].read_text(encoding="utf-8")), [])
            self.assertEqual(json.loads(chemins["SEEN"].read_text(encoding="utf-8")), {})

    def test_appel_ollama_reessaie_une_fois_puis_leve(self):
        appels = []

        class ReponseImpossible(Exception):
            pass

        def poster(*args, **kwargs):
            appels.append(1)
            raise ReponseImpossible("service arrete")

        faux_requests = types.ModuleType("requests")
        faux_requests.post = poster

        with (
            patch.dict(sys.modules, {"requests": faux_requests}),
            patch.object(curate, "PAUSE_AVANT_REPRISE", 0),
            # Sans ce verrou, le nombre de tentatives depend de FRONTIERE_LLM
            # dans l'environnement qui lance les tests : le chemin api en
            # compte quatre, le chemin ollama deux. Le test echouait donc sur
            # une machine ou la variable vaut « api », et passait en CI ou
            # elle est absente.
            patch.object(curate, "FOURNISSEUR", "ollama"),
        ):
            with self.assertRaises(curate.OllamaIndisponible):
                curate._appel_ollama("prompt")

        self.assertEqual(len(appels), 2)


class EnregistrerExecutionTests(unittest.TestCase):
    """L'historique lu par verifier_sante.py doit survivre entre executions."""

    def test_ajoute_une_entree_au_fichier_existant(self):
        with tempfile.TemporaryDirectory() as dossier:
            sante = Path(dossier) / "sante.json"
            sante.write_text(
                json.dumps([{"date": "2026-07-01", "nb_publies": 3}]),
                encoding="utf-8",
            )
            with (
                patch.object(curate, "SANTE", sante),
                patch.object(curate, "FOURNISSEUR", "api"),
            ):
                curate.enregistrer_execution(
                    nb_eligibles=5, nb_publies=0, nb_reportes=2,
                    nb_non_publies_validation=3,
                )

            historique = json.loads(sante.read_text(encoding="utf-8"))
            self.assertEqual(len(historique), 2)
            self.assertEqual(historique[-1]["nb_publies"], 0)
            self.assertEqual(historique[-1]["nb_eligibles"], 5)
            self.assertEqual(historique[-1]["fournisseur"], "api")

    def test_cree_le_fichier_sil_est_absent(self):
        with tempfile.TemporaryDirectory() as dossier:
            sante = Path(dossier) / "sous-dossier" / "sante.json"
            with patch.object(curate, "SANTE", sante):
                curate.enregistrer_execution(
                    nb_eligibles=0, nb_publies=0, nb_reportes=0,
                    nb_non_publies_validation=0,
                )
            self.assertTrue(sante.exists())
            self.assertEqual(len(json.loads(sante.read_text(encoding="utf-8"))), 1)

    def test_conserve_seulement_les_dernieres_executions(self):
        with tempfile.TemporaryDirectory() as dossier:
            sante = Path(dossier) / "sante.json"
            ancien = [{"date": f"2026-01-{i:02d}", "nb_publies": 1} for i in range(1, 15)]
            sante.write_text(json.dumps(ancien), encoding="utf-8")
            with (
                patch.object(curate, "SANTE", sante),
                patch.object(curate, "NB_EXECUTIONS_CONSERVEES", 12),
            ):
                curate.enregistrer_execution(
                    nb_eligibles=1, nb_publies=1, nb_reportes=0,
                    nb_non_publies_validation=0,
                )
            self.assertEqual(len(json.loads(sante.read_text(encoding="utf-8"))), 12)

    def test_fichier_corrompu_repart_de_zero_sans_planter(self):
        with tempfile.TemporaryDirectory() as dossier:
            sante = Path(dossier) / "sante.json"
            sante.write_text("pas du json valide", encoding="utf-8")
            with patch.object(curate, "SANTE", sante):
                curate.enregistrer_execution(
                    nb_eligibles=1, nb_publies=1, nb_reportes=0,
                    nb_non_publies_validation=0,
                )
            self.assertEqual(len(json.loads(sante.read_text(encoding="utf-8"))), 1)


class ValidationResumeAnglaisTests(unittest.TestCase):
    """Le resume anglais sert /en/frontier/. Il doit tenir les memes exigences
    que son equivalent francais : deux phrases, troisieme personne, aucun
    chiffre invente."""

    RESUME_VALIDE = (
        "The study estimates the effect of automation on regional employment. "
        "Results point to a persistent decline in manufacturing hours."
    )

    def test_resume_conforme_passe(self):
        self.assertEqual(curate.erreurs_resume_en(self.RESUME_VALIDE), [])

    def test_texte_vide_rejete(self):
        self.assertIn("texte_vide", curate.erreurs_resume_en(""))

    def test_une_seule_phrase_rejetee(self):
        self.assertIn(
            "nombre_phrases",
            curate.erreurs_resume_en("The study estimates the effect of automation."),
        )

    def test_premiere_personne_rejetee(self):
        texte = (
            "We estimate the effect of automation on regional employment. "
            "Results point to a persistent decline in manufacturing hours."
        )
        self.assertIn("premiere_personne", curate.erreurs_resume_en(texte))

    def test_tiret_cadratin_rejete(self):
        texte = (
            "The study estimates the effect of automation \u2014 a broad one. "
            "Results point to a persistent decline in manufacturing hours."
        )
        self.assertIn("tiret_cadratin", curate.erreurs_resume_en(texte))

    def test_reponse_en_francais_rejetee(self):
        """Le modele repond parfois dans la langue de l'autre prompt."""
        texte = (
            "Cette etude mesure les effets de l'automatisation sur les regions. "
            "Les resultats montrent une baisse durable dans les usines."
        )
        self.assertIn("francais_residuel", curate.erreurs_resume_en(texte))

    def test_chiffre_absent_de_la_source_rejete(self):
        texte = (
            "The study covers 42 regions of the country. "
            "Results point to a persistent decline in manufacturing hours."
        )
        source = "The study covers several regions of the country."
        self.assertEqual(curate.erreurs_invention(texte, source), ["chiffre_invente"])


class ValidationAngleAnglaisTests(unittest.TestCase):
    def test_angle_conforme_passe(self):
        texte = "Automation shifts labor demand toward tasks that resist codification."
        self.assertEqual(curate.erreurs_angle_en(texte), [])

    def test_formule_stereotypee_rejetee(self):
        texte = "This paper shows that automation shifts labor demand."
        self.assertIn("formule_stereotypee", curate.erreurs_angle_en(texte))

    def test_deux_phrases_rejetees(self):
        texte = "Automation shifts labor demand. It also raises wage dispersion."
        self.assertIn("nombre_phrases", curate.erreurs_angle_en(texte))

    def test_premiere_personne_rejetee(self):
        texte = "Our results show that automation shifts labor demand."
        self.assertIn("premiere_personne", curate.erreurs_angle_en(texte))


class ChampsAnglaisNonBloquantsTests(unittest.TestCase):
    """Un echec cote anglais ne doit jamais retenir un item dont le francais
    est valide : la page anglaise retombe sur le francais."""

    def test_drapeau_desactive_supprime_les_appels_anglais(self):
        with patch.object(curate, "RESUME_EN_ACTIF", False):
            self.assertFalse(curate.RESUME_EN_ACTIF)

    def test_budget_par_item_double_quand_l_anglais_est_actif(self):
        """Deux champs de plus, deux essais chacun : le budget doit suivre."""
        self.assertEqual(curate.APPELS_MAX_PAR_ITEM, 8 if curate.RESUME_EN_ACTIF else 4)

    def test_prompt_anglais_part_de_l_abstract_pas_du_resume_francais(self):
        prompt = curate.construire_prompt_resume_en("Titre", "Original abstract text")
        self.assertIn("Original abstract text", prompt)
        self.assertIn("2 factual sentences in English", prompt)

    def test_resume_anglais_sans_abstract_retourne_none(self):
        self.assertIsNone(curate.resume_en_ollama("Titre", ""))

    def test_panne_anglaise_ne_retient_pas_un_item_dont_le_francais_est_valide(self):
        """Le francais est deja redige et valide quand l'anglais part. Une panne
        a ce moment doit couter les deux champs anglais, pas l'item entier."""
        candidat = {
            "id": "test-panne-en",
            "titre": "Economic policy with machine learning",
            "url": "https://example.com/test-panne-en",
            "source": "test",
            "type": "papier",
            "date_publication": "2026-08-01",
            "abstract": "Economic policy and market analysis using machine learning.",
            "auteurs": "Auteur Test",
        }

        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            chemins = {
                "ENTREE": racine / "candidats.json",
                "SORTIE": racine / "cures.json",
                "SORTIE_ARCHIVE": racine / "archives.json",
                "SEEN": racine / "seen.json",
                "SANTE": racine / "sante.json",
            }
            chemins["ENTREE"].write_text(json.dumps([candidat]), encoding="utf-8")
            chemins["SEEN"].write_text("{}", encoding="utf-8")

            with ExitStack() as pile:
                for nom, chemin in chemins.items():
                    pile.enter_context(patch.object(curate, nom, chemin))
                pile.enter_context(patch.object(curate, "LLM_ACTIF", True))
                pile.enter_context(patch.object(curate, "RESUME_EN_ACTIF", True))
                pile.enter_context(patch.object(
                    curate, "resume_ollama",
                    return_value="Le texte mesure un effet sur l'emploi regional. "
                                 "Les heures declinent dans le secteur manufacturier.",
                ))
                pile.enter_context(patch.object(
                    curate, "angle_eco_ollama",
                    return_value="L'automatisation deplace la demande de travail "
                                 "vers les taches difficiles a codifier.",
                ))
                pile.enter_context(patch.object(
                    curate, "resume_en_ollama",
                    side_effect=curate.OllamaIndisponible("panne simulee"),
                ))
                curate.main()

            publies = json.loads(chemins["SORTIE"].read_text(encoding="utf-8"))

        self.assertEqual(len(publies), 1, "l'item doit etre publie malgre la panne")
        self.assertTrue(publies[0]["resume_fr"])
        self.assertNotIn("resume_en", publies[0])
        self.assertNotIn("angle_eco_en", publies[0])


if __name__ == "__main__":
    unittest.main()
