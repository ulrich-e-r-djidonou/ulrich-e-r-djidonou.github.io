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


class ChampJsonTests(unittest.TestCase):
    source = {
        "lecteur": "champ_json",
        "url": "https://exemple.test/indicators.json",
        "champ": "lastUpdated",
        "gabarit": "Mise à jour le {date}",
    }

    def test_lit_le_champ_nomme(self):
        def recuperer(url):
            return json.dumps({"lastUpdated": "2026-08-05", "regions": {}})

        self.assertEqual(
            etat_projets.lire_source(self.source, recuperer),
            ("2026-08-05", "lastUpdated"),
        )

    def test_champ_absent_leve_une_erreur(self):
        with self.assertRaises(ValueError):
            etat_projets.date_depuis_champ_json({"regions": {}}, "lastUpdated")

    def test_champ_vide_leve_une_erreur(self):
        # Un champ present mais vide passerait le test d'existence et
        # produirait une etiquette sans date.
        with self.assertRaises(ValueError):
            etat_projets.date_depuis_champ_json({"lastUpdated": ""}, "lastUpdated")


class DerniereDateCsvTests(unittest.TestCase):
    source = {
        "lecteur": "derniere_date_csv",
        "url": "https://exemple.test/tone_index.csv",
        "colonne": "date",
        "gabarit": "Communiqués analysés jusqu'au {date}",
    }

    def test_prend_la_date_la_plus_recente(self):
        def recuperer(url):
            return "date,tone\n2026-07-15,-1.0\n2009-01-20,-1.0\n"

        self.assertEqual(
            etat_projets.lire_source(self.source, recuperer), ("2026-07-15", "csv")
        )

    def test_l_ordre_des_lignes_n_a_pas_d_importance(self):
        # Une reprise de collecte peut ajouter une ligne ancienne en fin de
        # fichier : lire la derniere ligne ferait alors reculer l'etiquette.
        croissant = "date\n2009-01-20\n2026-07-15\n"
        decroissant = "date\n2026-07-15\n2009-01-20\n"
        self.assertEqual(
            etat_projets.derniere_date_csv(croissant, "date"),
            etat_projets.derniere_date_csv(decroissant, "date"),
        )

    def test_lignes_sans_date_ignorees(self):
        texte = "date,tone\n,\n2026-07-15,-1.0\n  ,\n"
        self.assertEqual(etat_projets.derniere_date_csv(texte, "date"), "2026-07-15")

    def test_colonne_entierement_vide_leve_une_erreur(self):
        with self.assertRaises(ValueError):
            etat_projets.derniere_date_csv("date,tone\n,\n", "date")


class SourcesDeclareesTests(unittest.TestCase):
    def test_chaque_source_a_un_lecteur_connu(self):
        connus = {"icie", "champ_json", "derniere_date_csv"}
        for identifiant, source in etat_projets.SOURCES.items():
            with self.subTest(projet=identifiant):
                self.assertIn(source.get("lecteur", "icie"), connus)

    def test_chaque_source_expose_une_url_pour_le_journal(self):
        # main() ecrit source["etat_json"] ou source["url"] dans le JSON :
        # une source qui n'a ni l'un ni l'autre ferait echouer l'ecriture
        # apres que la date a ete lue.
        for identifiant, source in etat_projets.SOURCES.items():
            with self.subTest(projet=identifiant):
                self.assertTrue(source.get("etat_json") or source.get("url"))

    def test_chaque_gabarit_accepte_une_date(self):
        for identifiant, source in etat_projets.SOURCES.items():
            with self.subTest(projet=identifiant):
                rendu = source["gabarit"].format(date="2 août 2026")
                self.assertIn("2 août 2026", rendu)

    def test_chaque_source_a_son_gabarit_anglais(self):
        # main() lit gabarit_en sans repli : une source ajoutee sans lui
        # ferait echouer l'execution apres la lecture de la date, et la page
        # anglaise garderait une etiquette perimee.
        for identifiant, source in etat_projets.SOURCES.items():
            with self.subTest(projet=identifiant):
                rendu = source["gabarit_en"].format(date="August 2, 2026")
                self.assertIn("August 2, 2026", rendu)


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

    def test_la_cle_choisit_la_langue_de_l_etiquette(self):
        # La page anglaise porte les memes attributs data-projet. Sans le
        # parametre, elle recevrait l'etiquette francaise.
        html, manquants = etat_projets.appliquer_etats(
            self.page,
            {"icie": {"etat": "Données jusqu'au 30 septembre 2026",
                      "etat_en": "Data through September 30, 2026"}},
            "etat_en",
        )
        self.assertIn("Data through September 30, 2026", html)
        self.assertNotIn("30 septembre 2026", html)
        self.assertEqual(manquants, [])

    def test_une_cle_absente_laisse_l_etiquette_en_place(self):
        # Un projet du JSON qui n'a pas encore d'etat_en, par exemple juste
        # apres l'ajout d'une source : mieux vaut une etiquette datee qu'une
        # etiquette vide.
        html, _ = etat_projets.appliquer_etats(
            self.page, {"icie": {"etat": "Données jusqu'au 30 septembre 2026"}}, "etat_en"
        )
        self.assertIn("Données jusqu'au 2 août 2026", html)

    def test_les_autres_cartes_ne_bougent_pas(self):
        html, _ = etat_projets.appliquer_etats(
            self.page, {"icie": {"etat": "Données jusqu'au 30 septembre 2026"}}
        )
        self.assertIn('<p class="project-etat" data-vivant>Mise à jour automatique</p>', html)

    def test_le_texte_distant_est_echappe(self):
        """Le texte derive de JSON publie par des sites tiers et finit dans
        projets.html sans relecture. Il ne doit pas pouvoir ouvrir de balise."""
        html, _ = etat_projets.appliquer_etats(
            self.page, {"icie": {"etat": "<img src=x onerror=alert(1)>"}}
        )

        self.assertNotIn("<img", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)

    def test_l_apostrophe_francaise_reste_intacte(self):
        """Garde-fou sur quote=False : echapper l'apostrophe rendrait pareil
        mais salirait le diff de chaque etiquette."""
        html, _ = etat_projets.appliquer_etats(
            self.page, {"icie": {"etat": "Données jusqu'au 30 septembre 2026"}}
        )

        self.assertIn("jusqu'au", html)
        self.assertNotIn("&#x27;", html)

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
