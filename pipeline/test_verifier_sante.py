import unittest

from pipeline import verifier_sante


def executions(*nb_publies_liste):
    return [
        {
            "date": f"2026-07-{10 + i:02d}",
            "fournisseur": "api",
            "nb_eligibles": 3,
            "nb_publies": nb,
            "nb_reportes": 0,
            "nb_rejetes_validation": 0,
        }
        for i, nb in enumerate(nb_publies_liste)
    ]


class ExecutionsAZeroPublicationTests(unittest.TestCase):
    def test_deux_zeros_consecutifs_declenchent_alerte(self):
        historique = executions(2, 0, 0)
        resultat = verifier_sante.executions_a_zero_publication(historique, 2)
        self.assertIsNotNone(resultat)
        self.assertEqual(len(resultat), 2)

    def test_une_seule_execution_a_zero_ne_declenche_rien(self):
        historique = executions(2, 3, 0)
        resultat = verifier_sante.executions_a_zero_publication(historique, 2)
        self.assertIsNone(resultat)

    def test_zero_puis_publication_reinitialise(self):
        historique = executions(0, 3, 0)
        resultat = verifier_sante.executions_a_zero_publication(historique, 2)
        self.assertIsNone(resultat)

    def test_historique_trop_court_ne_declenche_rien(self):
        historique = executions(0)
        resultat = verifier_sante.executions_a_zero_publication(historique, 2)
        self.assertIsNone(resultat)

    def test_historique_vide_ne_declenche_rien(self):
        resultat = verifier_sante.executions_a_zero_publication([], 2)
        self.assertIsNone(resultat)

    def test_trois_zeros_consecutifs_declenchent_alerte(self):
        historique = executions(0, 0, 0)
        resultat = verifier_sante.executions_a_zero_publication(historique, 2)
        self.assertIsNotNone(resultat)


if __name__ == "__main__":
    unittest.main()
