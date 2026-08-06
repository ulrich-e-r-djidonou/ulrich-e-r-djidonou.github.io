import json
import unittest

from pipeline import etat_projets


class FormaterDateTests(unittest.TestCase):
    def test_format_courant(self):
        self.assertEqual(
            etat_projets.formater_date_francaise("2026-08-02"), "2 août 2026"
        )

    def test_premier_du_mois_prend_er(self):
        self.assertEqual(
            etat_projets.formater_date_francaise("2026-09-01"), "1er septembre 2026"
        )

    def test_les_accents_des_mois_sont_conserves(self):
        # Une date sans accent trahirait le reste du site et signalerait un
        # contournement d'encodage plutot qu'une correction.
        self.assertEqual(
            etat_projets.formater_date_francaise("2026-02-14"), "14 février 2026"
        )
        self.assertEqual(
            etat_projets.formater_date_francaise("2026-12-25"), "25 décembre 2026"
        )


class LireSourceTests(unittest.TestCase):
    source = {
        "etat_json": "https://exemple.test/etat.json",
        "page": "https://exemple.test/",
        "gabarit": "Données jusqu'au {date}",
    }

    def test_etat_json_est_prefere(self):
        def recuperer(url):
            if url.endswith("etat.json"):
                return json.dumps({"date_donnees": "2026-08-02"})
            raise AssertionError("le dashboard ne devait pas etre telecharge")

        self.assertEqual(
            etat_projets.lire_source(self.source, recuperer), ("2026-08-02", "etat.json")
        )

    def test_repli_sur_le_dashboard_quand_etat_json_manque(self):
        dashboard = (
            '<script id="dashboard-data" type="application/json">'
            '{"recent": {"latestDate": "2026-07-19"}}</script>'
        )

        def recuperer(url):
            if url.endswith("etat.json"):
                raise ValueError("404")
            return dashboard

        self.assertEqual(
            etat_projets.lire_source(self.source, recuperer), ("2026-07-19", "dashboard")
        )

    def test_horodatage_complet_reduit_a_la_date(self):
        def recuperer(url):
            return json.dumps({"date_donnees": "2026-08-02T00:00:00Z"})

        self.assertEqual(
            etat_projets.lire_source(self.source, recuperer)[0], "2026-08-02"
        )


class AppliquerEtatsTests(unittest.TestCase):
    page = (
        '<article class="project-card">\n'
        '  <p class="project-etat" data-projet="icie">Données jusqu\'au 2 août 2026</p>\n'
        "</article>\n"
        '<article class="project-card">\n'
        '  <p class="project-etat" data-vivant>Mise à jour automatique</p>\n'
        "</article>\n"
    )

    def test_la_carte_ciblee_est_reecrite(self):
        html, manquants = etat_projets.appliquer_etats(
            self.page, {"icie": {"etat": "Données jusqu'au 30 septembre 2026"}}
        )
        self.assertIn(
            '<p class="project-etat" data-projet="icie">Données jusqu\'au 30 septembre 2026</p>',
            html,
        )
        self.assertEqual(manquants, [])

    def test_les_autres_cartes_ne_bougent_pas(self):
        html, _ = etat_projets.appliquer_etats(
            self.page, {"icie": {"etat": "Données jusqu'au 30 septembre 2026"}}
        )
        self.assertIn('<p class="project-etat" data-vivant>Mise à jour automatique</p>', html)

    def test_une_carte_absente_est_signalee(self):
        # Sans ce signal, le JSON avancerait pendant que la page afficherait
        # une vieille date, exactement le mensonge que ce module evite.
        _, manquants = etat_projets.appliquer_etats(
            self.page, {"gtrends": {"etat": "Données jusqu'au 1er mai 2026"}}
        )
        self.assertEqual(manquants, ["gtrends"])

    def test_reecriture_idempotente(self):
        etat = {"icie": {"etat": "Données jusqu'au 2 août 2026"}}
        html, _ = etat_projets.appliquer_etats(self.page, etat)
        self.assertEqual(html, self.page)


class DateDepuisDashboardTests(unittest.TestCase):
    def test_bloc_absent_leve_une_erreur(self):
        with self.assertRaises(ValueError):
            etat_projets.date_depuis_dashboard("<html><body>rien</body></html>")

    def test_champ_absent_leve_une_erreur(self):
        html = (
            '<script id="dashboard-data" type="application/json">'
            '{"recent": {}}</script>'
        )
        with self.assertRaises(ValueError):
            etat_projets.date_depuis_dashboard(html)


if __name__ == "__main__":
    unittest.main()
