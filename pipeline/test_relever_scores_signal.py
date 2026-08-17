import unittest

from pipeline import relever_scores_signal as releve


def executions(*scores_max):
    """Historique ou None represente une recolte vide."""
    return [
        {"date": f"2026-07-{10 + i:02d}", "nb_publies": 3, "score_max": score}
        for i, score in enumerate(scores_max)
    ]


class ScoresRelevesTests(unittest.TestCase):
    def test_ecarte_les_recoltes_vides(self):
        # None ne dit rien sur le plancher : seule une recolte reelle mesure.
        self.assertEqual(releve.scores_releves(executions(6, None, 4)), [6, 4])

    def test_ecarte_les_lignes_sans_le_champ(self):
        historique = [{"date": "2026-07-01", "nb_publies": 2}]
        self.assertEqual(releve.scores_releves(historique), [])

    def test_conserve_un_zero_qui_est_une_vraie_mesure(self):
        self.assertEqual(releve.scores_releves(executions(0, 6)), [0, 6])


class PartAvecSignalTests(unittest.TestCase):
    def test_compte_les_scores_atteignant_le_seuil(self):
        self.assertEqual(releve.part_avec_signal([3, 6, 8, 4], 6), 0.5)

    def test_liste_vide_ne_donne_pas_de_part(self):
        self.assertIsNone(releve.part_avec_signal([], 6))


class SeuilRecommandeTests(unittest.TestCase):
    def test_recommande_d_abaisser_un_plancher_trop_haut(self):
        # Plancher 8 : 20% des executions, trop peu. Plancher 6 : 40%, dans la
        # fourchette.
        scores = [8, 8, 6, 6] + [3] * 6
        self.assertEqual(releve.seuil_recommande(scores, 8), 6)

    def test_ne_recommande_rien_quand_le_plancher_actuel_convient(self):
        scores = [6, 6, 6, 3, 3, 3]
        self.assertIsNone(releve.seuil_recommande(scores, 6))

    def test_retient_le_plancher_le_plus_eleve_de_la_fourchette(self):
        # A couverture acceptable egale, un plancher haut selectionne mieux.
        scores = [8, 8, 6, 6, 3, 3]
        self.assertEqual(releve.seuil_recommande(scores, 3), 6)

    def test_aucun_candidat_ne_donne_aucune_recommandation(self):
        # Tous identiques : chaque plancher donne 100% ou 0%, jamais la
        # fourchette visee.
        self.assertIsNone(releve.seuil_recommande([5, 5, 5, 5], 6))


class RendreReleveTests(unittest.TestCase):
    def test_sans_mesure_le_releve_le_dit(self):
        lignes = releve.rendre_releve(executions(None, None))
        self.assertIn("Aucun score_max journalise", lignes[0])

    def test_refuse_de_recommander_sur_trop_peu_d_executions(self):
        texte = "\n".join(releve.rendre_releve(executions(3, 3, 4), seuil_actuel=6))
        self.assertIn("Trop peu d'executions", texte)
        self.assertNotIn("Piste :", texte)

    def test_recommande_au_dela_du_minimum(self):
        scores = [8, 8, 6, 6] + [3] * 6
        texte = "\n".join(releve.rendre_releve(executions(*scores), seuil_actuel=8))
        self.assertIn("Piste : abaisser SEUIL_SIGNAL de 8 a 6", texte)

    def test_distingue_un_plancher_correct_d_une_distribution_inutilisable(self):
        # Le message ne doit pas lire « tout va bien » quand aucun plancher ne
        # convient : ici un seul 6 sur dix, et rien ne tombe dans la fourchette.
        scores = [6] + [4] * 9
        texte = "\n".join(releve.rendre_releve(executions(*scores), seuil_actuel=6))
        self.assertIn("trop concentres", texte)
        self.assertIn("C'est le score lui-meme", texte)
        self.assertNotIn("Rien a changer", texte)

    def test_annonce_la_distribution_et_le_plancher_actuel(self):
        texte = "\n".join(releve.rendre_releve(executions(6, 3), seuil_actuel=6))
        self.assertIn("Plancher actuel : 6.", texte)
        self.assertIn("Executions mesurees : 2.", texte)
        self.assertIn("<- actuel", texte)


if __name__ == "__main__":
    unittest.main()
