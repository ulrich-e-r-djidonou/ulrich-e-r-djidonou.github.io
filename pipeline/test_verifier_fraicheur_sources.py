"""Tests du diagnostic de fraicheur des sources.

Aucun de ces tests ne touche au reseau. C'est delibere : un test qui
interroge un flux tiers echoue le jour ou ce tiers est lent, en panne, ou
simplement calme, et apprend a tout le monde a ignorer un echec rouge. La
partie qui fait du reseau (sonder, compteurs_rss) est volontairement mince
et sans decision ; toute la logique de classement vit dans diagnostic(),
qui ne prend que des nombres.

    python -m unittest pipeline.test_verifier_fraicheur_sources
"""

import unittest

from pipeline import verifier_fraicheur_sources as sonde


class DiagnosticTests(unittest.TestCase):
    def test_une_source_qui_alimente_est_active(self):
        etat, _ = sonde.diagnostic(
            nb_items=15, nb_dans_fenetre=10, nb_retenus=3, jours_depuis_derniere=2
        )

        self.assertEqual(etat, "ACTIVE")
        self.assertFalse(sonde.est_muette(etat))

    def test_un_flux_vide_est_signale(self):
        etat, explication = sonde.diagnostic(
            nb_items=0, nb_dans_fenetre=0, nb_retenus=0, jours_depuis_derniere=None
        )

        self.assertEqual(etat, "VIDE")
        self.assertIn("aucune entree", explication)

    def test_un_flux_qui_ne_publie_plus_est_dormant(self):
        """Cas rencontre le 12 aout 2026 : les notes analytiques du personnel
        de la Banque du Canada repondaient 200 avec dix entrees valides, dont
        la plus recente avait huit mois."""
        etat, explication = sonde.diagnostic(
            nb_items=10, nb_dans_fenetre=0, nb_retenus=0, jours_depuis_derniere=243
        )

        self.assertEqual(etat, "DORMANTE")
        self.assertIn("243", explication)

    def test_des_filtres_trop_etroits_sont_distingues_d_un_flux_mort(self):
        """La distinction porte tout l'interet du module : un flux vivant dont
        les filtres ecartent tout ne se corrige pas comme un flux mort."""
        etat, explication = sonde.diagnostic(
            nb_items=15, nb_dans_fenetre=10, nb_retenus=0, jours_depuis_derniere=1
        )

        self.assertEqual(etat, "FILTREE")
        self.assertIn("filtres", explication)

    def test_une_source_sans_dates_mais_qui_retient_reste_active(self):
        """Le flux « new » de NBER ne porte aucune date et s'appuie sur
        date_repli. Compte sur ses seules dates, il paraissait muet alors
        qu'il alimentait la veille : le nombre d'entrees retenues tranche
        avant tout compteur intermediaire."""
        etat, _ = sonde.diagnostic(
            nb_items=22, nb_dans_fenetre=0, nb_retenus=3, jours_depuis_derniere=None
        )

        self.assertEqual(etat, "ACTIVE")

    def test_un_compteur_non_observable_n_est_pas_annonce_comme_vide(self):
        """Les collecteurs arxiv, crossref et github_commits filtrent dans la
        requete : leurs compteurs avant filtrage n'existent pas. Annoncer
        « flux vide » serait une affirmation sans preuve, le defaut meme que
        ce module cherche a corriger ailleurs."""
        etat, explication = sonde.diagnostic(
            nb_items=None, nb_dans_fenetre=0, nb_retenus=0, jours_depuis_derniere=None
        )

        self.assertEqual(etat, "SANS RETOUR")
        self.assertNotIn("vide", explication.lower())
        self.assertTrue(sonde.est_muette(etat))

    def test_une_source_recente_sans_entree_dans_la_fenetre(self):
        etat, _ = sonde.diagnostic(
            nb_items=12, nb_dans_fenetre=0, nb_retenus=0, jours_depuis_derniere=45
        )

        self.assertEqual(etat, "HORS FENETRE")

    def test_le_seuil_de_dormance_n_est_pas_franchi_a_la_limite(self):
        """Au seuil exact, la source est encore consideree comme calme."""
        etat, _ = sonde.diagnostic(
            nb_items=10,
            nb_dans_fenetre=0,
            nb_retenus=0,
            jours_depuis_derniere=sonde.SEUIL_DORMANCE_JOURS,
        )

        self.assertNotEqual(etat, "DORMANTE")

        etat_apres, _ = sonde.diagnostic(
            nb_items=10,
            nb_dans_fenetre=0,
            nb_retenus=0,
            jours_depuis_derniere=sonde.SEUIL_DORMANCE_JOURS + 1,
        )

        self.assertEqual(etat_apres, "DORMANTE")


class EstMuetteTests(unittest.TestCase):
    def test_seul_active_n_est_pas_muet(self):
        for etat in (
            "VIDE",
            "DORMANTE",
            "HORS FENETRE",
            "FILTREE",
            "SANS RETOUR",
            "ECHEC",
            "INCONNUE",
        ):
            with self.subTest(etat=etat):
                self.assertTrue(sonde.est_muette(etat))

        self.assertFalse(sonde.est_muette("ACTIVE"))


class ChargerSourcesTests(unittest.TestCase):
    def test_ne_renvoie_que_les_sources_actives(self):
        sources = sonde.charger_sources()

        self.assertTrue(sources, "sources.yaml ne declare aucune source active")
        for source in sources:
            with self.subTest(source=source.get("id")):
                self.assertTrue(source.get("actif"))

    def test_chaque_source_active_a_un_collecteur(self):
        """Une faute de frappe sur `type` produirait une source qui ne leve
        aucune erreur et ne collecte rien, exactement le silence que ce
        module cherche a rendre visible."""
        from pipeline import collect

        for source in sonde.charger_sources():
            with self.subTest(source=source.get("id")):
                self.assertTrue(
                    hasattr(collect, f"collecter_{source['type']}"),
                    f"aucun collecteur pour le type '{source['type']}'",
                )


if __name__ == "__main__":
    unittest.main()
