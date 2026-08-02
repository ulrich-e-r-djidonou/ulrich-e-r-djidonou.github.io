import unittest

from pipeline.benchmark.reconstruire_corpus import (
    nettoyer_texte_source,
    reconstruire_abstract_openalex,
)
from pipeline.benchmark.comparer_modeles import normaliser_sortie
from pipeline.benchmark.generer_rapport import calculer_metriques


class ReconstructionCorpusTests(unittest.TestCase):
    def test_nettoie_un_abstract_crossref(self):
        source = "<jats:p>Un premier résultat &amp; une conclusion.</jats:p>"

        self.assertEqual(
            nettoyer_texte_source(source),
            "Un premier résultat & une conclusion.",
        )

    def test_reconstruit_un_abstract_openalex(self):
        index = {
            "Les": [0],
            "gains": [1],
            "augmentent": [2],
            "vite.": [3],
        }

        self.assertEqual(
            reconstruire_abstract_openalex(index),
            "Les gains augmentent vite.",
        )

    def test_remplace_le_tiret_cadratin(self):
        source = f"Avant{chr(0x2014)}après"

        self.assertEqual(normaliser_sortie(source), "Avant,après")


class RapportTests(unittest.TestCase):
    def test_agrege_les_echecs_et_le_temps(self):
        resultats = {
            "items": {
                "item-1": {
                    "modele": {
                        "publiable": False,
                        "resume": {
                            "essais": [{
                                "erreurs": ["nombre_phrases"],
                                "duree_secondes": 2.0,
                            }],
                        },
                        "angle": {
                            "essais": [{
                                "erreurs": ["formule_stereotypee"],
                                "duree_secondes": 1.0,
                            }],
                        },
                    },
                },
            },
        }

        metriques = calculer_metriques(resultats, ["modele"])["modele"]

        self.assertEqual(metriques["items"], 1)
        self.assertEqual(metriques["resume_nombre_phrases"], 1)
        self.assertEqual(metriques["formule_stereotypee"], 1)
        self.assertEqual(metriques["non_publiables"], 1)
        self.assertEqual(metriques["duree_secondes"], 3.0)


if __name__ == "__main__":
    unittest.main()
