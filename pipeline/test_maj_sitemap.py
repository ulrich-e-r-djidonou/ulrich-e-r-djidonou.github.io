import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import maj_sitemap


def entree(url, lastmod, alternates=True):
    # Forme reellement publiee : trois xhtml:link entre <loc> et <lastmod>.
    # Le constat du 19 aout venait de tests ecrits sur un format sans eux.
    liens = ""
    if alternates:
        liens = "".join(
            f'\n    <xhtml:link rel="alternate" hreflang="{cle}" href="{url}"/>'
            for cle in ("fr", "en", "x-default")
        )
    return (
        f"  <url>\n    <loc>{url}</loc>{liens}\n    <lastmod>{lastmod}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n  </url>\n"
    )


def sitemap(dates):
    corps = "".join(entree(url, d) for url, d in dates.items())
    corps += entree("https://djidonou.com/frontiere/", "2026-11-16")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        f"{corps}</urlset>\n"
    )


class DepotTemporaire:
    """Depot git jetable ou chaque page recoit des commits dates."""

    def __init__(self, dossier):
        self.racine = Path(dossier)
        self._git("init", "-q")

    def _git(self, *args, date_commit=None):
        env = dict(os.environ)
        if date_commit:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date_commit}T12:00:00+00:00"
        subprocess.run(
            ["git", "-C", str(self.racine), "-c", "user.name=Test",
             "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", *args],
            check=True, capture_output=True, env=env,
        )

    def commit(self, fichier, message, date_commit):
        chemin = self.racine / fichier
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("a", encoding="utf-8") as f:
            f.write(f"{message}\n")
        self._git("add", fichier)
        # Bac a sable de test : les crochets globaux du poste n'ont rien a y voir.
        self._git("commit", "-q", "--no-verify", "-m", message, date_commit=date_commit)


class MajSitemapTests(unittest.TestCase):
    def setUp(self):
        # Lances par le crochet pre-commit, ces tests heritent de GIT_DIR et
        # GIT_INDEX_FILE : git ignorerait alors le -C du bac a sable et
        # commiterait dans le vrai depot. On les retire le temps du test.
        env_propre = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        patch = mock.patch.dict(os.environ, env_propre, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        self._dossier = tempfile.TemporaryDirectory()
        self.depot = DepotTemporaire(self._dossier.name)
        for fichier in maj_sitemap.PAGES.values():
            self.depot.commit(fichier, f"creation de {fichier}", "2026-08-19")

    def tearDown(self):
        self._dossier.cleanup()

    def ecrire_sitemap(self, dates):
        (self.depot.racine / "sitemap.xml").write_text(sitemap(dates), encoding="utf-8")

    def test_les_commits_de_robots_sont_ignores(self):
        self.depot.commit("projets.html", "projets: etiquettes de fraicheur au 2026-11-17", "2026-11-17")
        self.depot.commit("index.html", "design: nouvelle accroche", "2026-10-31")

        attendues = maj_sitemap.dates_attendues(self.depot.racine)

        self.assertEqual(attendues["https://djidonou.com/projets.html"], "2026-08-19")
        self.assertEqual(attendues["https://djidonou.com/"], "2026-10-31")

    def test_ecriture_corrige_les_dates_sans_toucher_la_frontiere(self):
        self.depot.commit("faq.html", "faq: nouvelle question", "2026-10-31")
        self.ecrire_sitemap({url: "2026-08-19" for url in maj_sitemap.PAGES})

        code = maj_sitemap.main([], racine=self.depot.racine)

        self.assertEqual(code, 0)
        resultat = (self.depot.racine / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn(
            "<loc>https://djidonou.com/faq.html</loc>", resultat
        )
        self.assertEqual(resultat.count("<lastmod>2026-10-31</lastmod>"), 1)
        self.assertEqual(resultat.count("<lastmod>2026-08-19</lastmod>"), 11)
        self.assertEqual(resultat.count("<lastmod>2026-11-16</lastmod>"), 1)
        self.assertEqual(resultat.count("<xhtml:link"), 3 * 13)

    def test_verifier_signale_une_date_en_retard_sans_ecrire(self):
        self.depot.commit("en/career.html", "career: mise a jour", "2026-10-31")
        self.ecrire_sitemap({url: "2026-08-19" for url in maj_sitemap.PAGES})
        avant = (self.depot.racine / "sitemap.xml").read_text(encoding="utf-8")

        code = maj_sitemap.main(["--verifier"], racine=self.depot.racine)

        self.assertEqual(code, 1)
        self.assertEqual((self.depot.racine / "sitemap.xml").read_text(encoding="utf-8"), avant)

    def test_verifier_accepte_un_sitemap_a_jour(self):
        self.ecrire_sitemap({url: "2026-08-19" for url in maj_sitemap.PAGES})

        self.assertEqual(maj_sitemap.main(["--verifier"], racine=self.depot.racine), 0)

    def test_entree_absente_leve_une_erreur_explicite(self):
        dates = {url: "2026-08-19" for url in maj_sitemap.PAGES}
        del dates["https://djidonou.com/contact.html"]
        self.ecrire_sitemap(dates)

        with self.assertRaisesRegex(ValueError, "contact.html"):
            maj_sitemap.main([], racine=self.depot.racine)


if __name__ == "__main__":
    unittest.main()
