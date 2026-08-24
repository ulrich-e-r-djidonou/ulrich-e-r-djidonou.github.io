"""Tests de pipeline/verifier_repli.py. Aucun appel reseau reel."""

import unittest
from unittest.mock import patch

import requests

from pipeline import verifier_repli


class _ReponseFictive:
    def __init__(self, code):
        self.status_code = code


def _erreur_http(code):
    erreur = requests.HTTPError("boum")
    erreur.response = _ReponseFictive(code)
    return erreur


class VerifierRepliTests(unittest.TestCase):
    def test_repli_non_configure_nomme_les_variables_manquantes(self):
        ok, message = verifier_repli.verifier(url="", modele="m", cle="")
        self.assertFalse(ok)
        self.assertIn("LLM_API_URL_REPLI", message)
        self.assertIn("LLM_API_CLE_REPLI", message)
        self.assertNotIn("LLM_API_MODELE_REPLI", message)

    def test_401_est_lu_comme_une_cle_refusee(self):
        with patch.object(verifier_repli.curate, "_requete_api", side_effect=_erreur_http(401)):
            ok, message = verifier_repli.verifier(url="u", modele="m", cle="c")
        self.assertFalse(ok)
        self.assertIn("401", message)
        self.assertIn("tronquee", message)

    def test_403_distingue_credits_absents_de_cle_refusee(self):
        with patch.object(verifier_repli.curate, "_requete_api", side_effect=_erreur_http(403)):
            ok, message = verifier_repli.verifier(url="u", modele="m", cle="c")
        self.assertFalse(ok)
        self.assertIn("credits", message)

    def test_service_injoignable_est_un_echec(self):
        panne = requests.ConnectionError("reseau coupe")
        with patch.object(verifier_repli.curate, "_requete_api", side_effect=panne):
            ok, message = verifier_repli.verifier(url="u", modele="m", cle="c")
        self.assertFalse(ok)
        self.assertIn("injoignable", message)

    def test_reponse_vide_est_un_echec(self):
        with patch.object(verifier_repli.curate, "_requete_api", return_value=""):
            ok, _ = verifier_repli.verifier(url="u", modele="m", cle="c")
        self.assertFalse(ok)

    def test_toute_reponse_non_vide_suffit(self):
        # C'est la joignabilite qu'on eprouve, pas la qualite du texte rendu.
        with patch.object(verifier_repli.curate, "_requete_api", return_value="n'importe quoi"):
            ok, message = verifier_repli.verifier(url="u", modele="m", cle="c")
        self.assertTrue(ok)
        self.assertIn("joignable", message)


if __name__ == "__main__":
    unittest.main()
