"""Tests de la detection de dates litterales a risque dans les tests.

La detection est testee sur du code fabrique, pas sur le depot reel : le
depot change, ces tests ne doivent pas suivre. Voir verifier_dates_tests.py
pour le cas reel qui a motive ce module
(test_axe_depot_utilise_created_pour_la_date, 13 aout 2026).

    python -m unittest pipeline.test_verifier_dates_tests
"""

import unittest

from pipeline import verifier_dates_tests as sonde


class TestsARisqueTests(unittest.TestCase):
    def test_date_litterale_avec_fenetre_jours_est_signalee(self):
        code = '''
def test_quelque_chose(self):
    source = {"fenetre_jours": 14}
    item = {"published": {"date-parts": [[2026, 7, 30]]}}
'''
        trouvailles = sonde.tests_a_risque(code)

        self.assertEqual(len(trouvailles), 1)
        self.assertEqual(trouvailles[0][0], "test_quelque_chose")

    def test_date_litterale_avec_dans_fenetre_est_signalee(self):
        code = '''
def test_autre_chose(self):
    date_pub = date(2026, 7, 30)
    self.assertTrue(dans_fenetre(date_pub, 14))
'''
        trouvailles = sonde.tests_a_risque(code)

        self.assertEqual(len(trouvailles), 1)

    def test_date_litterale_sans_fenetre_n_est_pas_signalee(self):
        """Le cas de DateCrossrefTests dans test_collect.py : la date
        litterale est le sujet du test de parsing, aucune fenetre glissante
        n'intervient. Le signaler serait un faux positif qui apprendrait a
        ignorer l'alerte."""
        code = '''
def test_date_complete_est_retenue(self):
    item = {"published": {"date-parts": [[2026, 7, 15]]}}
    self.assertEqual(date_crossref(item), date(2026, 7, 15))
'''
        self.assertEqual(sonde.tests_a_risque(code), [])

    def test_fenetre_sans_date_litterale_n_est_pas_signalee(self):
        """Le cas de test_axe_depot_utilise_created_pour_la_date corrige le
        13 aout 2026 : la fenetre reste, mais la date est desormais relative
        a aujourd'hui, plus de date litterale a signaler."""
        code = '''
def test_axe_depot_utilise_created_pour_la_date(self):
    source = {"fenetre_jours": 14}
    creation = date.today() - timedelta(days=5)
'''
        self.assertEqual(sonde.tests_a_risque(code), [])

    def test_une_fonction_qui_n_est_pas_un_test_est_ignoree(self):
        code = '''
def _reponse(self, items):
    source = {"fenetre_jours": 14}
    item = {"published": {"date-parts": [[2026, 7, 30]]}}
'''
        self.assertEqual(sonde.tests_a_risque(code), [])

    def test_plusieurs_tests_a_risque_sont_tous_rapportes(self):
        code = '''
def test_premier(self):
    source = {"fenetre_jours": 60}
    item = {"published": {"date-parts": [[2026, 7, 1]]}}

def test_second(self):
    source = {"fenetre_jours": 30}
    item = {"published": {"date-parts": [[2026, 6, 1]]}}
'''
        trouvailles = sonde.tests_a_risque(code)

        self.assertEqual({nom for nom, _ in trouvailles}, {"test_premier", "test_second"})

    def test_une_date_iso_en_chaine_est_reconnue(self):
        code = '''
def test_avec_chaine(self):
    self.assertTrue(dans_fenetre("2026-07-30", 14))
'''
        self.assertEqual(len(sonde.tests_a_risque(code)), 1)

    def test_un_code_syntaxiquement_invalide_ne_leve_pas(self):
        """Ne doit jamais faire planter la CI sur un fichier casse : un autre
        controle (verifier_html, la simple execution des tests) le fera deja
        savoir, avec un message plus utile."""
        self.assertEqual(sonde.tests_a_risque("def test_incomplet("), [])


class FichiersDeTestsTests(unittest.TestCase):
    def test_ce_fichier_s_exclut_lui_meme(self):
        """Sans cela, le scan ci-dessous se signalerait lui-meme : ses
        fixtures fabriquees contiennent, en chaines de caracteres, du code
        qui a la forme d'une date a risque sans en etre une."""
        noms = {f.name for f in sonde.fichiers_de_tests()}
        self.assertNotIn("test_verifier_dates_tests.py", noms)

    def test_le_depot_reel_ne_contient_aucune_date_a_risque(self):
        """Filet de securite : le controle doit rester vert sur le depot
        lui-meme, pas seulement sur des exemples fabriques."""
        anomalies = []
        for fichier in sonde.fichiers_de_tests():
            code = fichier.read_text(encoding="utf-8")
            for nom_test, ligne in sonde.tests_a_risque(code):
                anomalies.append(f"{fichier.name}:{ligne} {nom_test}")

        self.assertEqual(anomalies, [])


if __name__ == "__main__":
    unittest.main()
