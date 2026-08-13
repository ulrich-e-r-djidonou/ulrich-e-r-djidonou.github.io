import unittest
from pathlib import Path
from pipeline import verifier_csp

PAGE_CONFORME = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self';">
    <title>Test</title>
</head>
<body></body>
</html>"""

PAGE_SANS_CSP = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <title>Test</title>
</head>
<body></body>
</html>"""

PAGE_UNSAFE_INLINE = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline';">
    <title>Test</title>
</head>
<body></body>
</html>"""

PAGE_UNSAFE_EVAL = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-eval';">
    <title>Test</title>
</head>
<body></body>
</html>"""


class VerifierCSPTests(unittest.TestCase):
    def test_page_conforme_passe(self):
        anomalies = verifier_csp.anomalies_csp(PAGE_CONFORME)
        self.assertEqual(anomalies, [])

    def test_page_sans_balise_csp_echoue(self):
        anomalies = verifier_csp.anomalies_csp(PAGE_SANS_CSP)
        self.assertTrue(len(anomalies) > 0)
        self.assertIn("balise meta Content-Security-Policy absente", anomalies[0][1])

    def test_page_avec_unsafe_inline_echoue(self):
        anomalies = verifier_csp.anomalies_csp(PAGE_UNSAFE_INLINE)
        self.assertTrue(len(anomalies) > 0)
        self.assertIn("unsafe-inline", anomalies[0][1])

    def test_page_avec_unsafe_eval_echoue(self):
        anomalies = verifier_csp.anomalies_csp(PAGE_UNSAFE_EVAL)
        self.assertTrue(len(anomalies) > 0)
        self.assertIn("unsafe-eval", anomalies[0][1])

    def test_exclusion_fichier_benchmark_est_appliquee(self):
        chemin_benchmark = Path("pipeline/benchmark/evaluation_aveugle.html")
        self.assertTrue(verifier_csp.est_page_exclue(chemin_benchmark))

    def test_page_site_non_exclue(self):
        chemin_index = Path("index.html")
        self.assertFalse(verifier_csp.est_page_exclue(chemin_index))


if __name__ == "__main__":
    unittest.main()
