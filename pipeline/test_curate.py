import json
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from pipeline import curate


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
        ):
            self.assertEqual(curate.modele_actif(), "modele-test")
        with patch.object(curate, "FOURNISSEUR", "ollama"):
            self.assertEqual(curate.modele_actif(), curate.OLLAMA_MODEL)


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
        with patch.object(curate, "BUDGET_APPELS", 20):
            curate._appels_effectues = 16
            self.assertFalse(curate.budget_epuise())
            curate._appels_effectues = 17
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


if __name__ == "__main__":
    unittest.main()
