import tempfile
import unittest
from pathlib import Path

from pipeline import verifier_hreflang


GABARIT = """<!doctype html>
<html lang="{langue}">
  <head>
    <link rel="canonical" href="https://djidonou.com{canonique}">
{alternates}
  </head>
  <body></body>
</html>
"""


def page(langue, canonique, alternates):
    lignes = "\n".join(
        f'    <link rel="alternate" hreflang="{cle}" href="{href}">'
        for cle, href in alternates
    )
    return GABARIT.format(langue=langue, canonique=canonique, alternates=lignes)


class VerifierPaireTests(unittest.TestCase):
    TRIPLET = (
        ("fr", "https://djidonou.com/projets.html"),
        ("en", "https://djidonou.com/en/projects.html"),
        ("x-default", "https://djidonou.com/projets.html"),
    )

    def ecrire(self, racine, alternates_fr=None, alternates_en=None):
        fr = racine / "projets.html"
        en = racine / "en" / "projects.html"
        en.parent.mkdir(parents=True, exist_ok=True)
        # Un tuple vide est une consigne, pas une absence de consigne : tester
        # explicitement contre None, sinon le cas « aucune annotation » retombe
        # sur le triplet complet et le test ne verifie plus rien.
        if alternates_fr is None:
            alternates_fr = self.TRIPLET
        if alternates_en is None:
            alternates_en = self.TRIPLET
        fr.write_text(page("fr", "/projets.html", alternates_fr), encoding="utf-8")
        en.write_text(
            page("en", "/en/projects.html", alternates_en), encoding="utf-8"
        )
        return racine

    def verifier(self, racine):
        return verifier_hreflang.verifier_paire(
            "projets.html",
            "en/projects.html",
            "/projets.html",
            "/en/projects.html",
            racine=racine,
        )

    def test_paire_reciproque_ne_signale_rien(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self.ecrire(Path(dossier))
            self.assertEqual(self.verifier(racine), [])

    def test_annotation_unilaterale_signalee(self):
        # L'etat exact du site avant ce controle : la page anglaise annonce sa
        # jumelle, la page francaise ne dit rien. Une paire hreflang qui n'est
        # pas reciproque peut etre ignoree des deux cotes.
        with tempfile.TemporaryDirectory() as dossier:
            racine = self.ecrire(Path(dossier), alternates_fr=())
            anomalies = self.verifier(racine)
            self.assertEqual(len(anomalies), 3)
            self.assertTrue(all(a.startswith("projets.html") for a in anomalies))

    def test_url_divergente_signalee(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self.ecrire(
                Path(dossier),
                alternates_en=(
                    ("fr", "https://djidonou.com/projets.html"),
                    ("en", "https://djidonou.com/en/projets.html"),
                    ("x-default", "https://djidonou.com/projets.html"),
                ),
            )
            anomalies = self.verifier(racine)
            self.assertEqual(len(anomalies), 1)
            self.assertIn("en/projets.html", anomalies[0])

    def test_x_default_doit_pointer_vers_le_francais(self):
        # Le francais est la langue par defaut du site : un x-default anglais
        # enverrait les visiteurs sans preference linguistique sur /en/.
        with tempfile.TemporaryDirectory() as dossier:
            racine = self.ecrire(
                Path(dossier),
                alternates_fr=(
                    ("fr", "https://djidonou.com/projets.html"),
                    ("en", "https://djidonou.com/en/projects.html"),
                    ("x-default", "https://djidonou.com/en/projects.html"),
                ),
            )
            anomalies = self.verifier(racine)
            self.assertEqual(len(anomalies), 1)
            self.assertIn("x-default", anomalies[0])

    def test_page_absente_signalee(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = self.ecrire(Path(dossier))
            (racine / "en" / "projects.html").unlink()
            anomalies = self.verifier(racine)
            self.assertEqual(anomalies, ["en/projects.html : page absente du disque"])


class SiteReelTests(unittest.TestCase):
    def test_le_site_publie_est_reciproque(self):
        self.assertEqual(verifier_hreflang.main(), 0)


if __name__ == "__main__":
    unittest.main()
