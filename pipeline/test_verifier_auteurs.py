"""Tests de pipeline.verifier_auteurs.

    python -m unittest pipeline.test_verifier_auteurs
"""

import unittest

from pipeline import verifier_auteurs


def item(source, auteurs):
    return {"source": source, "auteurs": auteurs}


class RegressionsCompletesTests(unittest.TestCase):
    def test_source_entierement_sans_auteur_est_signalee(self):
        items = [item("VoxEU / CEPR", ""), item("VoxEU / CEPR", "")]
        resultat = verifier_auteurs.regressions_completes(items)
        self.assertEqual(resultat, {"VoxEU / CEPR": 2})

    def test_source_partiellement_sans_auteur_nest_pas_signalee(self):
        # Regression du 2026-08-11 : 3 items VoxEU restes sans auteur pour
        # des raisons documentees au cas par cas, pas une extraction cassee.
        items = [item("VoxEU / CEPR", "Alice Martin"), item("VoxEU / CEPR", "")]
        self.assertEqual(verifier_auteurs.regressions_completes(items), {})

    def test_source_avec_tous_ses_auteurs_nest_pas_signalee(self):
        items = [item("NBER", "Alice Martin"), item("NBER", "Bob Roy")]
        self.assertEqual(verifier_auteurs.regressions_completes(items), {})

    def test_source_connue_sans_auteurs_nest_jamais_signalee(self):
        items = [
            item("Banque centrale europeenne (BCE), working papers", ""),
            item("Banque centrale europeenne (BCE), working papers", ""),
        ]
        self.assertEqual(verifier_auteurs.regressions_completes(items), {})

    def test_plusieurs_sources_cassees_triees_par_nombre_ditems(self):
        items = [
            item("Source A", ""), item("Source A", ""),
            item("Source B", ""), item("Source B", ""), item("Source B", ""),
        ]
        resultat = verifier_auteurs.regressions_completes(items)
        self.assertEqual(list(resultat.items()), [("Source B", 3), ("Source A", 2)])

    def test_liste_vide_ne_signale_rien(self):
        self.assertEqual(verifier_auteurs.regressions_completes([]), {})


class MainTests(unittest.TestCase):
    def test_flux_absent_ne_fait_pas_echouer(self):
        original = verifier_auteurs.FLUX
        verifier_auteurs.FLUX = original.parent / "flux-introuvable-pour-le-test.json"
        try:
            self.assertEqual(verifier_auteurs.main(), 0)
        finally:
            verifier_auteurs.FLUX = original

    def test_flux_reel_ne_signale_aucune_source_cassee(self):
        # Verifie l'archive publiee elle-meme, pas seulement des donnees
        # synthetiques : c'est elle qui a declenche ce module.
        self.assertEqual(verifier_auteurs.main(), 0)


if __name__ == "__main__":
    unittest.main()
