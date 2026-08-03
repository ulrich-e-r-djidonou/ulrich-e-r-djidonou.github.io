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


class GenererJsonldFluxTests(unittest.TestCase):
    def test_distingue_la_redaction_du_travail_cite(self):
        entrees = [
            {
                "id": "arxiv-1",
                "titre": "Un papier externe",
                "url": "https://arxiv.org/abs/1",
                "source": "arXiv",
                "date_publication": "2026-08-01",
                "resume_fr": "Resume en francais.",
                "angle_eco": "Angle economique.",
                "themes": ["llm", "travail-emploi"],
                "auteurs": "A. Auteur, B. Auteur",
            }
        ]

        donnees = publish.generer_jsonld_flux(entrees)

        self.assertEqual(donnees["@type"], "ItemList")
        item = donnees["itemListElement"][0]["item"]
        self.assertEqual(item["author"], {"@id": "https://djidonou.com/#person"})
        self.assertIn("Resume en francais.", item["description"])
        self.assertIn("Angle economique.", item["description"])
        self.assertEqual(item["citation"]["url"], "https://arxiv.org/abs/1")
        self.assertEqual(item["citation"]["author"], "A. Auteur, B. Auteur")
        self.assertEqual(item["keywords"], "llm, travail-emploi")

    def test_retombe_sur_la_source_sans_auteurs(self):
        entrees = [{
            "id": "x", "titre": "T", "url": "https://x.example/1",
            "source": "VoxEU", "date_publication": "2026-08-01",
            "resume_fr": "R.", "angle_eco": "", "themes": [], "auteurs": "",
        }]

        donnees = publish.generer_jsonld_flux(entrees)

        self.assertEqual(
            donnees["itemListElement"][0]["item"]["citation"]["author"],
            "VoxEU",
        )

    def test_liste_vide_produit_un_itemlist_vide(self):
        donnees = publish.generer_jsonld_flux([])
        self.assertEqual(donnees["itemListElement"], [])


class InjecterJsonldFluxTests(unittest.TestCase):
    def test_remplace_le_bloc_flux_jsonld_sans_toucher_au_reste(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.html"
            index.write_text(
                """<html><head>
    <script type="application/ld+json">
    { "@type": "CollectionPage" }
    </script>

    <script type="application/ld+json" id="flux-jsonld">
    []
    </script>
</head></html>""",
                encoding="utf-8",
            )

            publish.injecter_jsonld_flux(
                {"@type": "ItemList", "itemListElement": [{"@type": "ListItem"}]},
                chemin_index=index,
            )

            resultat = index.read_text(encoding="utf-8")
            self.assertIn('"@type": "CollectionPage"', resultat)
            self.assertIn('"itemListElement"', resultat)
            bloc = resultat.split('id="flux-jsonld">', 1)[1].split("</script>", 1)[0]
            self.assertEqual(
                json.loads(bloc),
                {"@type": "ItemList", "itemListElement": [{"@type": "ListItem"}]},
            )

    def test_bloc_absent_leve_une_erreur(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.html"
            index.write_text("<html></html>", encoding="utf-8")

            with self.assertRaises(ValueError):
                publish.injecter_jsonld_flux({"@type": "ItemList"}, chemin_index=index)


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
