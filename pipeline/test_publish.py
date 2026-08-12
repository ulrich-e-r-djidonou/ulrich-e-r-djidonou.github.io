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


class InventaireArchivesTests(unittest.TestCase):
    """Un mois d'archive vide existe comme fichier mais n'a rien a montrer.
    Le lister donnait un bouton menant a un ecran vide, ce qu'un visiteur
    lit comme une panne plutot que comme une absence de contenu."""

    def _dossier(self, contenus):
        dossier = Path(self.enveloppe.name)
        for mois, entrees in contenus.items():
            (dossier / f"{mois}.json").write_text(
                json.dumps(entrees, ensure_ascii=False), encoding="utf-8"
            )
        return dossier

    def setUp(self):
        self.enveloppe = tempfile.TemporaryDirectory()
        self.addCleanup(self.enveloppe.cleanup)

    def test_un_mois_vide_n_est_pas_liste(self):
        dossier = self._dossier({
            "2026-06": [],
            "2026-07": [{"id": "a"}, {"id": "b"}],
        })

        mois, comptes = publish.inventorier_archives(dossier)

        self.assertEqual(mois, ["2026-07"])
        self.assertNotIn("2026-06", comptes)

    def test_les_comptes_suivent_les_mois_listes(self):
        dossier = self._dossier({
            "2026-07": [{"id": "a"}, {"id": "b"}],
            "2026-08": [{"id": "c"}],
        })

        mois, comptes = publish.inventorier_archives(dossier)

        self.assertEqual(mois, ["2026-07", "2026-08"])
        self.assertEqual(comptes, {"2026-07": 2, "2026-08": 1})

    def test_aucune_archive_ne_leve_pas(self):
        mois, comptes = publish.inventorier_archives(Path(self.enveloppe.name))

        self.assertEqual(mois, [])
        self.assertEqual(comptes, {})


class EchappementBaliseScriptTests(unittest.TestCase):
    """Le titre d'un item vient brut du flux de la source. S'il contient
    </script>, le JSON-LD injecte dans frontiere/index.html fermerait la
    balise et le reste passerait pour du HTML executable, sur une page
    committee deux fois par semaine sans relecture humaine."""

    TITRE_PIEGE = "</script><img src=x onerror=alert(1)>"

    def test_un_titre_piege_ne_ferme_pas_la_balise(self):
        charge = publish.echapper_pour_balise_script(
            json.dumps({"headline": self.TITRE_PIEGE}, ensure_ascii=False)
        )

        self.assertNotIn("</script>", charge)
        self.assertNotIn("<", charge)

    def test_la_valeur_relue_est_identique_a_l_originale(self):
        """L'echappement doit etre transparent : un moteur de recherche ou un
        LLM qui relit le bloc doit voir exactement le titre d'origine."""
        charge = publish.echapper_pour_balise_script(
            json.dumps({"headline": self.TITRE_PIEGE}, ensure_ascii=False)
        )

        self.assertEqual(json.loads(charge)["headline"], self.TITRE_PIEGE)

    def test_le_bloc_injecte_dans_la_page_reste_clos(self):
        with tempfile.TemporaryDirectory() as dossier:
            index = Path(dossier) / "index.html"
            index.write_text(
                '<script type="application/ld+json" id="flux-jsonld">\n'
                "{}\n</script>",
                encoding="utf-8",
            )
            entrees = [{
                "titre": self.TITRE_PIEGE,
                "url": "https://example.test/a",
                "date_publication": "2026-08-01",
                "resume_fr": "resume",
                "source": "Source",
            }]

            publish.injecter_jsonld_flux(
                publish.generer_jsonld_flux(entrees), chemin_index=index
            )

            contenu = index.read_text(encoding="utf-8")
            # Une seule fermeture : celle de la balise ouverte plus haut.
            self.assertEqual(contenu.count("</script>"), 1)
            self.assertNotIn("<img", contenu)


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
