"""Tests de la resolution locale des liens du site.

Aucun test ne touche au reseau. C'est le meme parti pris que pour la sonde
de fraicheur : un test qui interroge un hote tiers echoue le jour ou ce tiers
est lent, et apprend a ignorer un echec rouge. Toute la decision testable
vit dans chemin_local(), qui ne consulte que le disque.

    python -m unittest pipeline.test_verifier_liens
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pipeline import verifier_liens


class CheminLocalTests(unittest.TestCase):
    """chemin_local() decide si une adresse appartient a ce depot."""

    def test_une_page_du_depot_est_resolue_sur_le_disque(self):
        """Le cas qui a fait echouer la CI le 13 aout 2026 : faq.html venait
        d'etre creee et n'etait pas encore deployee, donc 404 par le reseau
        alors que le fichier etait bien la."""
        chemin = verifier_liens.chemin_local("https://djidonou.com/faq.html")

        self.assertIsNotNone(chemin)
        self.assertEqual(chemin.name, "faq.html")

    def test_la_racine_resout_vers_index_html(self):
        chemin = verifier_liens.chemin_local("https://djidonou.com/")

        self.assertIsNotNone(chemin)
        self.assertEqual(chemin.name, "index.html")

    def test_un_repertoire_resout_vers_son_index(self):
        chemin = verifier_liens.chemin_local("https://djidonou.com/frontiere/")

        self.assertIsNotNone(chemin)
        self.assertEqual(chemin.name, "index.html")
        self.assertEqual(chemin.parent.name, "frontiere")

    def test_un_fichier_non_html_du_depot_est_resolu(self):
        chemin = verifier_liens.chemin_local("https://djidonou.com/frontiere/feed.xml")

        self.assertIsNotNone(chemin)
        self.assertEqual(chemin.name, "feed.xml")

    def test_un_projet_heberge_ailleurs_n_est_pas_resolu_localement(self):
        """geoecon-pulse et les autres projets vivent dans leurs propres
        depots, servis sous le meme domaine. Les resoudre ici les declarerait
        morts a tort : seul le reseau peut les verifier."""
        self.assertIsNone(verifier_liens.chemin_local("https://djidonou.com/geoecon-pulse/"))

    def test_un_hote_tiers_n_est_jamais_resolu_localement(self):
        self.assertIsNone(verifier_liens.chemin_local("https://www.nber.org/papers/w12345"))

    def test_le_prefixe_www_du_site_est_reconnu(self):
        chemin = verifier_liens.chemin_local("https://www.djidonou.com/faq.html")

        self.assertIsNotNone(chemin)
        self.assertEqual(chemin.name, "faq.html")

    def test_une_remontee_de_repertoire_ne_sort_pas_du_depot(self):
        """Les URL viennent des pages du depot, pas d'un tiers, mais une
        resolution de chemin qui accepte « ../ » finit toujours par lire
        ailleurs qu'on croit.

        La cible est un fichier cree pour ce test hors du depot, et non un
        chemin imaginaire : sans cela le test passerait parce que le fichier
        n'existe pas, sans rien dire du garde-fou.
        """
        with tempfile.TemporaryDirectory(dir=verifier_liens.RACINE.parent) as dossier:
            cible = Path(dossier) / "temoin.txt"
            cible.write_text("hors du depot", encoding="utf-8")
            self.assertTrue(cible.is_file(), "le fichier temoin doit exister")

            url = f"https://djidonou.com/../{Path(dossier).name}/temoin.txt"
            self.assertIsNone(verifier_liens.chemin_local(url))

    def test_une_page_supprimee_du_depot_n_est_pas_resolue(self):
        """Retomber sur le reseau est voulu : lui seul distingue une page
        supprimee d'un projet heberge ailleurs."""
        self.assertIsNone(
            verifier_liens.chemin_local("https://djidonou.com/page-qui-n-existe-pas.html")
        )


class VerifierTests(unittest.TestCase):
    def test_une_page_du_depot_est_saine_sans_appel_reseau(self):
        """Si verifier() appelait le reseau ici, le test le saurait :
        requests est remplace par une bombe."""
        def bombe(*args, **kwargs):
            raise AssertionError("verifier() ne doit pas interroger le reseau "
                                 "pour une page presente dans le depot")

        original = verifier_liens.requests.get
        verifier_liens.requests.get = bombe
        try:
            self.assertIsNone(verifier_liens.verifier("https://djidonou.com/faq.html"))
        finally:
            verifier_liens.requests.get = original


class BloquantTests(unittest.TestCase):
    """Un lien qu'on n'a pas pu joindre n'est pas un lien mort.

    archive.org repond 503 aux adresses IP des runners GitHub tout en
    repondant 200 depuis un poste ordinaire (verifie trois fois le 13 aout
    2026). Faire echouer la CI la-dessus demanderait de « corriger » un lien
    valide. Le reseau est simule ici : ces tests ne sortent pas de la machine.
    """

    def _reponse(self, code, url="https://exemple.invalid/page"):
        return SimpleNamespace(
            status_code=code, history=[], url=url, close=lambda: None
        )

    def _avec_reponse(self, code):
        original = verifier_liens.requests.get
        dormir = verifier_liens.time.sleep
        verifier_liens.requests.get = lambda *a, **k: self._reponse(code)
        verifier_liens.time.sleep = lambda _: None  # pas d'attente reelle
        try:
            return verifier_liens.verifier("https://exemple.invalid/page")
        finally:
            verifier_liens.requests.get = original
            verifier_liens.time.sleep = dormir

    def test_un_503_persistant_est_signale_sans_bloquer(self):
        probleme = self._avec_reponse(503)

        self.assertIsNotNone(probleme)
        self.assertFalse(probleme.bloquant)
        self.assertIn("503", probleme.raison)
        self.assertIn("pas un lien mort", probleme.raison)

    def test_un_429_persistant_ne_bloque_pas(self):
        self.assertFalse(self._avec_reponse(429).bloquant)

    def test_un_404_bloque(self):
        probleme = self._avec_reponse(404)

        self.assertIsNotNone(probleme)
        self.assertTrue(probleme.bloquant)
        self.assertIn("404", probleme.raison)

    def test_un_403_bloque(self):
        self.assertTrue(self._avec_reponse(403).bloquant)

    def test_un_200_est_sain(self):
        self.assertIsNone(self._avec_reponse(200))

    def test_un_code_transitoire_est_reessaye_puis_accepte_s_il_se_retablit(self):
        """Le cas nominal de la reprise : le premier essai echoue, le second
        passe. Sans cela le controle echouerait au hasard des hebergeurs."""
        codes = [503, 200]
        original = verifier_liens.requests.get
        dormir = verifier_liens.time.sleep
        verifier_liens.requests.get = lambda *a, **k: self._reponse(codes.pop(0))
        verifier_liens.time.sleep = lambda _: None
        try:
            self.assertIsNone(verifier_liens.verifier("https://exemple.invalid/page"))
        finally:
            verifier_liens.requests.get = original
            verifier_liens.time.sleep = dormir

        self.assertEqual(codes, [], "les deux reponses simulees doivent etre consommees")

    def test_une_authentification_bloque(self):
        reponse = SimpleNamespace(
            status_code=200,
            history=[],
            url="https://exemple.invalid/-/login",
            close=lambda: None,
        )
        original = verifier_liens.requests.get
        verifier_liens.requests.get = lambda *a, **k: reponse
        try:
            probleme = verifier_liens.verifier("https://exemple.invalid/tableau")
        finally:
            verifier_liens.requests.get = original

        self.assertIsNotNone(probleme)
        self.assertTrue(probleme.bloquant)


class ConfigurationTests(unittest.TestCase):
    def test_les_codes_transitoires_couvrent_la_limitation_de_debit(self):
        """498 vient d'archive.org le 13 aout 2026, 429 est le code standard."""
        self.assertIn(498, verifier_liens.CODES_TRANSITOIRES)
        self.assertIn(429, verifier_liens.CODES_TRANSITOIRES)

    def test_un_404_n_est_pas_traite_comme_transitoire(self):
        """Sinon un lien reellement mort serait reessaye puis oublie."""
        self.assertNotIn(404, verifier_liens.CODES_TRANSITOIRES)
        self.assertNotIn(403, verifier_liens.CODES_TRANSITOIRES)


if __name__ == "__main__":
    unittest.main()
