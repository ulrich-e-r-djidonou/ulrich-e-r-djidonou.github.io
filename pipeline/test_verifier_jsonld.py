import tempfile
import unittest
from pathlib import Path

from pipeline import verifier_jsonld


def ecrire_page(dossier, *blocs):
    corps = "\n".join(
        f'<script type="application/ld+json">\n{bloc}\n</script>' for bloc in blocs
    )
    chemin = Path(dossier) / "page.html"
    chemin.write_text(f"<html><head>{corps}</head></html>", encoding="utf-8")
    return chemin


class ExtraireBlocsTests(unittest.TestCase):
    def test_trouve_plusieurs_blocs(self):
        with tempfile.TemporaryDirectory() as dossier:
            chemin = ecrire_page(dossier, '{"@type": "Person"}', '{"@type": "WebSite"}')
            self.assertEqual(len(verifier_jsonld.extraire_blocs(chemin)), 2)


class ValiderBlocTests(unittest.TestCase):
    def test_bloc_json_invalide_est_signale(self):
        erreurs = []
        verifier_jsonld.valider_bloc("{ pas du json", 1, Path("x.html"), erreurs)
        self.assertEqual(len(erreurs), 1)
        self.assertIn("JSON invalide", erreurs[0])

    def test_champ_requis_manquant_est_signale(self):
        erreurs = []
        verifier_jsonld.valider_bloc(
            '{"@type": "Person", "name": "U"}', 1, Path("x.html"), erreurs
        )
        self.assertEqual(len(erreurs), 1)
        self.assertIn("url", erreurs[0])

    def test_bloc_complet_ne_produit_aucune_erreur(self):
        erreurs = []
        verifier_jsonld.valider_bloc(
            '{"@type": "Person", "name": "U", "url": "https://x.example/"}',
            1,
            Path("x.html"),
            erreurs,
        )
        self.assertEqual(erreurs, [])

    def test_graph_est_parcouru(self):
        erreurs = []
        verifier_jsonld.valider_bloc(
            '{"@graph": [{"@type": "Person", "name": "U"}]}',
            1,
            Path("x.html"),
            erreurs,
        )
        self.assertEqual(len(erreurs), 1)

    def test_itemlist_valide_chaque_creative_work(self):
        bloc = """
        {
          "@type": "ItemList",
          "itemListElement": [
            {"@type": "ListItem", "position": 1, "item": {
              "@type": "CreativeWork",
              "headline": "T",
              "url": "https://djidonou.com/frontiere/",
              "author": {"@id": "https://djidonou.com/#person"},
              "datePublished": "2026-08-01",
              "citation": {"url": "https://x.example/1", "author": "A"}
            }}
          ]
        }
        """
        erreurs = []
        verifier_jsonld.valider_bloc(bloc, 1, Path("x.html"), erreurs)
        self.assertEqual(erreurs, [])

    def test_citation_sans_auteur_est_signalee(self):
        bloc = """
        {
          "@type": "ItemList",
          "itemListElement": [
            {"@type": "ListItem", "position": 1, "item": {
              "@type": "CreativeWork",
              "headline": "T",
              "url": "https://djidonou.com/frontiere/",
              "author": {"@id": "https://djidonou.com/#person"},
              "datePublished": "2026-08-01",
              "citation": {"url": "https://x.example/1", "author": ""}
            }}
          ]
        }
        """
        erreurs = []
        verifier_jsonld.valider_bloc(bloc, 1, Path("x.html"), erreurs)
        self.assertTrue(any("citation.author" in erreur for erreur in erreurs))

    def test_listitem_sans_item_exploitable_est_signale(self):
        bloc = '{"@type": "ItemList", "itemListElement": [{"position": 1}]}'
        erreurs = []
        verifier_jsonld.valider_bloc(bloc, 1, Path("x.html"), erreurs)
        self.assertTrue(any("sans champ 'item'" in erreur for erreur in erreurs))


class MainSurPagesReellesTests(unittest.TestCase):
    def test_les_pages_du_site_sont_valides(self):
        self.assertEqual(verifier_jsonld.main(), 0)


if __name__ == "__main__":
    unittest.main()
