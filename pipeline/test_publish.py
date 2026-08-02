import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline import publish


class SynchroniserSitemapTests(unittest.TestCase):
    def test_met_a_jour_uniquement_la_date_de_la_frontiere(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            sitemap = racine / "sitemap.xml"
            meta = racine / "meta.json"
            sitemap.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://djidonou.com/</loc>
    <lastmod>2026-07-11</lastmod>
  </url>
  <url>
    <loc>https://djidonou.com/frontiere/</loc>
    <lastmod>2026-07-11</lastmod>
  </url>
</urlset>
""",
                encoding="utf-8",
            )
            meta.write_text(
                json.dumps({"derniere_mise_a_jour": "2026-07-30"}),
                encoding="utf-8",
            )

            publish.synchroniser_sitemap(sitemap, meta)

            resultat = sitemap.read_text(encoding="utf-8")
            self.assertIn(
                "<loc>https://djidonou.com/</loc>\n    <lastmod>2026-07-11</lastmod>",
                resultat,
            )
            self.assertIn(
                "<loc>https://djidonou.com/frontiere/</loc>\n    <lastmod>2026-07-30</lastmod>",
                resultat,
            )


class RepartirSelectionTests(unittest.TestCase):
    def test_separe_un_score_deux_d_un_score_trois(self):
        entrees = [
            {"id": "archive", "score": 2, "date_publication": "2026-08-01"},
            {"id": "selection", "score": 3, "date_publication": "2026-08-01"},
        ]

        selection, archives = publish.repartir_selection_et_archives(
            entrees,
            date(2026, 5, 3),
        )

        self.assertEqual([entree["id"] for entree in selection], ["selection"])
        self.assertEqual([entree["id"] for entree in archives], ["archive"])


if __name__ == "__main__":
    unittest.main()
