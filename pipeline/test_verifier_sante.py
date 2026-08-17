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


def executions_signal(*drapeaux):
    """Historique ou chaque drapeau est True, False, ou None pour une ligne
    ancienne, ecrite avant que signal_designe existe."""
    lignes = []
    for i, drapeau in enumerate(drapeaux):
        ligne = {
            "date": f"2026-07-{10 + i:02d}",
            "fournisseur": "api",
            "nb_publies": 3,
        }
        if drapeau is not None:
            ligne["signal_designe"] = drapeau
            ligne["score_max"] = 3 if drapeau is False else 8
        lignes.append(ligne)
    return lignes


class ExecutionsSansSignalTests(unittest.TestCase):
    def test_quatre_absences_consecutives_declenchent_l_alerte(self):
        historique = executions_signal(True, False, False, False, False)
        resultat = verifier_sante.executions_sans_signal(historique, 4)
        self.assertIsNotNone(resultat)
        self.assertEqual(len(resultat), 4)

    def test_trois_absences_ne_suffisent_pas(self):
        historique = executions_signal(False, False, False)
        self.assertIsNone(verifier_sante.executions_sans_signal(historique, 4))

    def test_un_signal_designe_reinitialise(self):
        historique = executions_signal(False, False, False, True)
        self.assertIsNone(verifier_sante.executions_sans_signal(historique, 4))

    def test_les_lignes_anterieures_au_champ_sont_ignorees(self):
        # Les executions d'avant le 17 aout 2026 ne portent pas le champ. Les
        # compter comme des absences declencherait l'alerte sur du passe qui
        # n'en savait rien, des la premiere execution a vide.
        historique = executions_signal(None, None, None, False)
        self.assertIsNone(verifier_sante.executions_sans_signal(historique, 4))

    def test_les_lignes_anciennes_ne_coupent_pas_une_serie(self):
        historique = executions_signal(False, None, False, False, False)
        resultat = verifier_sante.executions_sans_signal(historique, 4)
        self.assertIsNotNone(resultat)

    def test_historique_vide_ne_declenche_rien(self):
        self.assertIsNone(verifier_sante.executions_sans_signal([], 4))


if __name__ == "__main__":
    unittest.main()
