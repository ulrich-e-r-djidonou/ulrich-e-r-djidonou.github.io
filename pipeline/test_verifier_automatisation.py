import unittest
from unittest.mock import patch

from pipeline import verifier_automatisation as verif

WORKFLOW = ".github/workflows/regenerer-flux.yml"


class ComparabiliteDesEtapesTests(unittest.TestCase):
    """Un run anterieur au workflow actuel n'a pas les memes noms d'etapes.

    Sans ce garde-fou, renommer une etape ferait passer toutes les etapes
    attendues pour manquantes dans l'historique, et le controle signalerait
    des pannes inexistantes. C'est arrive le 3 aout 2026.
    """

    def _git(self, reponses):
        def faux_git(*arguments):
            return reponses.get(arguments[0])
        return faux_git

    def test_accepte_un_run_posterieur_au_dernier_changement(self):
        reponses = {"log": "abc123", "cat-file": "", "merge-base": ""}
        with patch.object(verif, "git", self._git(reponses)):
            self.assertTrue(
                verif.execute_le_workflow_actuel({"headSha": "def456"}, WORKFLOW)
            )

    def test_refuse_un_run_anterieur_au_dernier_changement(self):
        # merge-base --is-ancestor sort en erreur, donc git() retourne None.
        reponses = {"log": "abc123", "cat-file": "", "merge-base": None}
        with patch.object(verif, "git", self._git(reponses)):
            self.assertFalse(
                verif.execute_le_workflow_actuel({"headSha": "def456"}, WORKFLOW)
            )

    def test_ne_bloque_pas_si_le_commit_est_inconnu_localement(self):
        # Un depot fraichement clone peut ne pas avoir le commit du run : mieux
        # vaut comparer les etapes que refuser tout controle.
        reponses = {"log": "abc123", "cat-file": None}
        with patch.object(verif, "git", self._git(reponses)):
            self.assertTrue(
                verif.execute_le_workflow_actuel({"headSha": "def456"}, WORKFLOW)
            )

    def test_ne_bloque_pas_sans_information(self):
        with patch.object(verif, "git", lambda *a: None):
            self.assertTrue(verif.execute_le_workflow_actuel({}, WORKFLOW))


if __name__ == "__main__":
    unittest.main()
