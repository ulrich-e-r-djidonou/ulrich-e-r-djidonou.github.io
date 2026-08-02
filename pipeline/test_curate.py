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
            entree.write_text(json.dumps([candidat]), encoding="utf-8")
            seen.write_text("{}", encoding="utf-8")

            with (
                patch.object(curate, "ENTREE", entree),
                patch.object(curate, "SORTIE", sortie),
                patch.object(curate, "SORTIE_ARCHIVE", sortie_archive),
                patch.object(curate, "SEEN", seen),
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
            entree.write_text(json.dumps([candidat]), encoding="utf-8")
            seen.write_text("{}", encoding="utf-8")

            with (
                patch.object(curate, "ENTREE", entree),
                patch.object(curate, "SORTIE", sortie),
                patch.object(curate, "SORTIE_ARCHIVE", sortie_archive),
                patch.object(curate, "SEEN", seen),
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


if __name__ == "__main__":
    unittest.main()
