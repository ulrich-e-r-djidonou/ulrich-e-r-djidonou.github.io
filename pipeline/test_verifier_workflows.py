import re
import unittest
from pathlib import Path
from unittest import mock

from pipeline import verifier_workflows

RACINE = Path(__file__).resolve().parent.parent


class SourceDepotsTests(unittest.TestCase):
    def test_jeton_personnel_interroge_les_depots_de_l_utilisateur(self):
        chemin, parametres = verifier_workflows.source_depots(True)
        self.assertEqual(chemin, "/user/repos")
        self.assertEqual(parametres["affiliation"], "owner")

    def test_sans_jeton_personnel_reste_sur_le_chemin_public(self):
        chemin, parametres = verifier_workflows.source_depots(False)
        self.assertEqual(chemin, f"/users/{verifier_workflows.PROPRIETAIRE}/repos")
        self.assertEqual(parametres["type"], "owner")
        # /user/repos repondrait 401 avec le jeton d'un run : le chemin public
        # est le seul qui accepte ce jeton.
        self.assertNotIn("affiliation", parametres)


class JetonTests(unittest.TestCase):
    def test_jeton_personnel_lu_dans_l_environnement(self):
        with mock.patch.dict("os.environ", {"JETON_DEPOTS": " abc "}, clear=True):
            self.assertEqual(verifier_workflows.jeton_personnel(), "abc")

    def test_secret_absent_donne_une_chaine_vide(self):
        # Un secret non defini arrive comme chaine vide, pas comme variable
        # absente : sans le strip, le controle croirait avoir un jeton.
        with mock.patch.dict("os.environ", {"JETON_DEPOTS": ""}, clear=True):
            self.assertEqual(verifier_workflows.jeton_personnel(), "")

    def test_jeton_personnel_prime_sur_celui_du_run(self):
        environnement = {"JETON_DEPOTS": "personnel", "GITHUB_TOKEN": "du-run"}
        with mock.patch.dict("os.environ", environnement, clear=True):
            self.assertEqual(
                verifier_workflows.entetes()["Authorization"], "Bearer personnel"
            )

    def test_repli_sur_le_jeton_du_run(self):
        with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "du-run"}, clear=True):
            self.assertEqual(
                verifier_workflows.entetes()["Authorization"], "Bearer du-run"
            )


class ResumePerimetreTests(unittest.TestCase):
    def test_en_local_les_prives_sont_denombres(self):
        depots = [{"private": True}, {"private": False}, {"private": True}]
        with mock.patch.dict("os.environ", {"AFFICHER_NOMS_PRIVES": "1"}, clear=True):
            resume = verifier_workflows.resume_perimetre(depots, True)
        self.assertIn("3 depots examines", resume)
        self.assertIn("2 prives", resume)

    def test_dans_un_journal_public_le_decompte_des_prives_est_tu(self):
        depots = [{"private": True}, {"private": False}, {"private": True}]
        with mock.patch.dict("os.environ", {}, clear=True):
            resume = verifier_workflows.resume_perimetre(depots, True)
        self.assertIn("3 depots examines", resume)
        self.assertNotIn("2 prives", resume)
        self.assertIn("AFFICHER_NOMS_PRIVES", resume)

    def test_sans_jeton_personnel_annonce_le_trou_de_couverture(self):
        # Un rapport muet sur ce qu'il ne voit pas se lirait comme une
        # couverture complete : c'est exactement le defaut que ce controle
        # existe pour eviter.
        resume = verifier_workflows.resume_perimetre([{"private": False}], False)
        self.assertIn("ne sont pas couverts", resume)
        self.assertIn("JETON_DEPOTS", resume)


class ExaminerDepotTests(unittest.TestCase):
    def depot(self, **extra):
        base = {"name": "gtrends", "full_name": "ulrich-e-r-djidonou/gtrends"}
        base.update(extra)
        return base

    def test_les_appels_passent_par_le_chemin_complet(self):
        appels = []

        def faux_api(chemin, **parametres):
            appels.append(chemin)
            if chemin.endswith("/actions/workflows"):
                return {"workflows": [{"id": 7, "name": "rafraichir-icie",
                                       "state": "active"}]}
            return {"workflow_runs": []}

        with mock.patch.object(verifier_workflows, "api", faux_api):
            verifier_workflows.examiner_depot(self.depot())

        self.assertTrue(all("ulrich-e-r-djidonou/gtrends" in c for c in appels))

    def faux_api_workflow_desactive(self, chemin, **parametres):
        if chemin.endswith("/actions/workflows"):
            return {"workflows": [{"id": 7, "name": "rafraichir-icie",
                                   "state": "disabled_inactivity"}]}
        return {"workflow_runs": []}

    def test_un_depot_prive_n_est_pas_nomme_dans_un_journal_public(self):
        # Ce controle tourne dans un depot public : son journal est lisible
        # par n'importe qui. Y ecrire « gtrends : rafraichir-icie en echec »
        # publierait le nom, l'objet et l'etat d'un projet ferme.
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(
                verifier_workflows, "api", self.faux_api_workflow_desactive
            ):
                problemes = verifier_workflows.examiner_depot(
                    self.depot(private=True), rang_prive=3
                )

        nom, titre, probleme = problemes[0]
        self.assertEqual(nom, "depot prive 3")
        self.assertNotIn("gtrends", nom)
        self.assertNotIn("rafraichir-icie", titre)
        self.assertIn("desactive", probleme)

    def test_en_local_le_depot_prive_reprend_son_nom(self):
        with mock.patch.dict("os.environ", {"AFFICHER_NOMS_PRIVES": "1"}, clear=True):
            with mock.patch.object(
                verifier_workflows, "api", self.faux_api_workflow_desactive
            ):
                problemes = verifier_workflows.examiner_depot(
                    self.depot(private=True), rang_prive=3
                )

        nom, titre, _ = problemes[0]
        self.assertEqual(nom, "gtrends (prive)")
        self.assertEqual(titre, "rafraichir-icie")

    def test_un_depot_public_garde_son_nom(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(
                verifier_workflows, "api", self.faux_api_workflow_desactive
            ):
                problemes = verifier_workflows.examiner_depot(self.depot())

        nom, titre, _ = problemes[0]
        self.assertEqual(nom, "gtrends")
        self.assertEqual(titre, "rafraichir-icie")

    def test_pages_est_lu_sans_filtre_d_evenement(self):
        # Les deploiements Pages ont l'evenement `dynamic`. Les filtrer sur
        # `schedule`, comme le reste, revenait a ne jamais les regarder.
        parametres_vus = []

        def faux_api(chemin, **parametres):
            if chemin.endswith("/actions/workflows"):
                return {"workflows": [{"id": 9, "name": "pages-build-deployment",
                                       "state": "active"}]}
            parametres_vus.append(parametres)
            return {"workflow_runs": []}

        with mock.patch.object(verifier_workflows, "api", faux_api):
            verifier_workflows.examiner_depot(self.depot())

        self.assertNotIn("event", parametres_vus[0])

    def test_les_autres_workflows_restent_filtres_sur_schedule(self):
        parametres_vus = []

        def faux_api(chemin, **parametres):
            if chemin.endswith("/actions/workflows"):
                return {"workflows": [{"id": 7, "name": "rafraichir-icie",
                                       "state": "active"}]}
            parametres_vus.append(parametres)
            return {"workflow_runs": []}

        with mock.patch.object(verifier_workflows, "api", faux_api):
            verifier_workflows.examiner_depot(self.depot())

        self.assertEqual(parametres_vus[0].get("event"), "schedule")

    def test_un_deploiement_pages_en_echec_est_signale(self):
        def faux_api(chemin, **parametres):
            if chemin.endswith("/actions/workflows"):
                return {"workflows": [{"id": 9, "name": "pages-build-deployment",
                                       "state": "active"}]}
            if parametres.get("status") == "success":
                return {"workflow_runs": []}
            return {"workflow_runs": [{"conclusion": "failure",
                                       "created_at": "2026-08-06T12:57:20Z"}]}

        with mock.patch.object(verifier_workflows, "api", faux_api):
            problemes = verifier_workflows.examiner_depot(self.depot())

        self.assertEqual(len(problemes), 1)
        self.assertIn("version precedente", problemes[0][2])

    def test_un_deploiement_pages_repare_n_est_pas_signale(self):
        def faux_api(chemin, **parametres):
            if chemin.endswith("/actions/workflows"):
                return {"workflows": [{"id": 9, "name": "pages-build-deployment",
                                       "state": "active"}]}
            if parametres.get("status") == "success":
                return {"workflow_runs": [{"created_at": "2026-08-06T18:20:00Z"}]}
            return {"workflow_runs": [{"conclusion": "failure",
                                       "created_at": "2026-08-06T12:57:20Z"}]}

        with mock.patch.object(verifier_workflows, "api", faux_api):
            problemes = verifier_workflows.examiner_depot(self.depot())

        self.assertEqual(problemes, [])

    def test_pages_ancien_mais_reussi_n_est_pas_signale(self):
        # Un depot sans commit depuis des mois n'a aucun deploiement recent,
        # et c'est normal : le controle de silence ne s'applique pas a Pages.
        def faux_api(chemin, **parametres):
            if chemin.endswith("/actions/workflows"):
                return {"workflows": [{"id": 9, "name": "pages-build-deployment",
                                       "state": "active"}]}
            return {"workflow_runs": [{"conclusion": "success",
                                       "created_at": "2024-01-01T00:00:00Z"}]}

        with mock.patch.object(verifier_workflows, "api", faux_api):
            problemes = verifier_workflows.examiner_depot(self.depot())

        self.assertEqual(problemes, [])

    def test_pages_garde_son_nom_sur_un_depot_prive(self):
        # Ce nom est identique sur tous les depots et ne revele rien du
        # projet : le masquer rendrait le rapport illisible sans rien
        # proteger.
        def faux_api(chemin, **parametres):
            if chemin.endswith("/actions/workflows"):
                return {"workflows": [{"id": 9, "name": "pages-build-deployment",
                                       "state": "disabled_manually"}]}
            return {"workflow_runs": []}

        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(verifier_workflows, "api", faux_api):
                problemes = verifier_workflows.examiner_depot(
                    self.depot(private=True), rang_prive=1
                )

        self.assertEqual(problemes[0][0], "depot prive 1")
        self.assertEqual(problemes[0][1], "pages-build-deployment")

    def test_les_deux_orthographes_de_pages_sont_reconnues(self):
        # L'API nomme le workflow `pages-build-deployment`, chaque execution
        # s'intitule « pages build and deployment ». L'ancienne liste des
        # ignores ne portait que la seconde : elle ne correspondait a rien.
        for titre in ("pages-build-deployment", "pages build and deployment",
                      "Pages-Build-Deployment"):
            with self.subTest(titre=titre):
                self.assertTrue(verifier_workflows.est_workflow_pages(titre))
                self.assertIsNone(verifier_workflows.evenement_surveille(titre))
        self.assertFalse(verifier_workflows.est_workflow_pages("rafraichir-icie"))
        self.assertEqual(
            verifier_workflows.evenement_surveille("rafraichir-icie"), "schedule"
        )

    def test_un_depot_sans_full_name_retombe_sur_le_proprietaire(self):
        appels = []

        def faux_api(chemin, **parametres):
            appels.append(chemin)
            return {"workflows": []}

        with mock.patch.object(verifier_workflows, "api", faux_api):
            verifier_workflows.examiner_depot({"name": "gtrends"})

        self.assertEqual(
            appels,
            [f"/repos/{verifier_workflows.PROPRIETAIRE}/gtrends/actions/workflows"],
        )


class ListeDesTestsEnCITests(unittest.TestCase):
    # Ce module est deja liste dans tests.yml : c'est ce qui fait tourner ce
    # garde-fou meme le jour ou un pipeline/test_nouveau.py, lui, ne l'est
    # pas encore. Un garde-fou place dans le fichier qu'il devrait detecter
    # ne se protegerait pas lui-meme. pipeline/ n'a pas de __init__.py (seul
    # pipeline/benchmark/__init__.py existe) : pas de unittest discover
    # fiable, d'ou la comparaison textuelle contre tests.yml.
    def test_tests_yml_liste_tous_les_modules_de_test(self):
        sur_disque = {
            str(f.relative_to(RACINE)).replace("\\", "/")[:-3].replace("/", ".")
            for f in list(RACINE.glob("pipeline/test_*.py"))
            + list(RACINE.glob("pipeline/benchmark/test_*.py"))
        }
        yml = (RACINE / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        en_ci = set(re.findall(r"^\s*(pipeline(?:\.\w+)*\.test_\w+)\s*\\?$", yml, re.M))
        self.assertEqual(
            sur_disque - en_ci,
            set(),
            "module(s) de test absent(s) de .github/workflows/tests.yml",
        )
        self.assertEqual(
            en_ci - sur_disque,
            set(),
            "module(s) liste(s) dans tests.yml sans fichier correspondant",
        )


if __name__ == "__main__":
    unittest.main()
