"""Tests du reetiquetage des entrees deja publiees.

Le risque propre a ce module n'est pas de rater une correction, c'est d'en
inventer une : il reecrit des donnees deja en ligne. Les tests portent donc
autant sur ce qu'il laisse tranquille que sur ce qu'il change.

    python -m unittest pipeline.test_migrer_etiquettes_types
"""

import unittest

from pipeline import migrer_etiquettes_types as migration


class EtiquetteAttendueTests(unittest.TestCase):
    def test_un_working_paper_est_un_papier(self):
        self.assertEqual(
            migration.etiquette_attendue("Reserve federale americaine (Fed), working papers"),
            "papier",
        )

    def test_une_revue_aea_est_un_article(self):
        self.assertEqual(
            migration.etiquette_attendue("Journal of Economic Perspectives"), "article"
        )

    def test_une_source_sans_regle_est_indecidable(self):
        """None, pas une valeur par defaut : une etiquette inventee serait
        pire que l'etiquette ancienne qu'elle remplacerait."""
        self.assertIsNone(migration.etiquette_attendue("Banque du Canada, publications"))
        self.assertIsNone(migration.etiquette_attendue("Source inconnue"))


class AnalyserTests(unittest.TestCase):
    def test_signale_l_inversion_sans_rien_modifier(self):
        entrees = [
            {"titre": "T", "source": "Journal of Economic Perspectives", "type": "papier"},
        ]

        changements, non_reconnues = migration.analyser(entrees)

        self.assertEqual(len(changements), 1)
        self.assertEqual(changements[0][2:], ("papier", "article"))
        self.assertEqual(non_reconnues, set())
        self.assertEqual(entrees[0]["type"], "papier", "analyser ne doit rien ecrire")

    def test_une_entree_deja_correcte_n_apparait_pas(self):
        entrees = [
            {"titre": "T", "source": "NBER, nouveaux working papers", "type": "papier"},
        ]

        changements, _ = migration.analyser(entrees)

        self.assertEqual(changements, [])

    def test_une_source_sans_regle_est_rapportee(self):
        entrees = [
            {"titre": "T", "source": "Banque du Canada, publications", "type": "article"},
        ]

        changements, non_reconnues = migration.analyser(entrees)

        self.assertEqual(changements, [])
        self.assertEqual(non_reconnues, {"Banque du Canada, publications"})


class AppliquerTests(unittest.TestCase):
    def test_corrige_les_deux_sens_de_l_inversion(self):
        entrees = [
            {"source": "Journal of Economic Perspectives", "type": "papier"},
            {"source": "Reserve federale americaine (Fed), working papers", "type": "article"},
        ]

        modifiees = migration.appliquer(entrees)

        self.assertEqual(modifiees, 2)
        self.assertEqual(entrees[0]["type"], "article")
        self.assertEqual(entrees[1]["type"], "papier")

    def test_ne_touche_pas_a_une_source_sans_regle(self):
        entrees = [{"source": "Banque du Canada, publications", "type": "article"}]

        modifiees = migration.appliquer(entrees)

        self.assertEqual(modifiees, 0)
        self.assertEqual(entrees[0]["type"], "article")

    def test_est_sur_a_repeter(self):
        """Une seconde execution ne doit rien trouver a faire."""
        entrees = [{"source": "Journal of Economic Perspectives", "type": "papier"}]

        migration.appliquer(entrees)

        self.assertEqual(migration.appliquer(entrees), 0)


class CoherenceAvecLaConventionTests(unittest.TestCase):
    def test_les_etiquettes_produites_sont_connues(self):
        valeurs = set(migration.ETIQUETTE_PAR_SOURCE.values()) | {"article"}

        self.assertTrue(valeurs.issubset({"papier", "article"}))

    def test_la_source_en_attente_n_a_pas_de_regle(self):
        """Garde-fou : si l'arbitrage est rendu et la regle ajoutee, il faut
        aussi retirer la source de SOURCES_SANS_DECISION, sinon le rapport
        continuerait de l'annoncer comme non tranchee."""
        for source in migration.SOURCES_SANS_DECISION:
            with self.subTest(source=source):
                self.assertIsNone(migration.etiquette_attendue(source))


if __name__ == "__main__":
    unittest.main()
