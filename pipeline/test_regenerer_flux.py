import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import curate, publish, regenerer_flux

# Bac a sable minimal pour injecter_jsonld_flux : sans le mocker sur
# publish.FRONTIERE_INDEX, ecrire_flux_anglais ecrirait dans le vrai
# frontiere/index.html du depot pendant les tests. C'est exactement ce qui
# s'est produit une fois : 58 entrees reelles ecrasees par une seule entree de
# test avant que le mock ci-dessous n'existe.
GABARIT_FRONTIERE_INDEX = (
    '<html><head><script type="application/ld+json" id="flux-jsonld">'
    "[]</script></head><body></body></html>"
)


class ChargerAbstractsTests(unittest.TestCase):
    def test_reunit_le_corpus_fige_et_la_derniere_collecte(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            corpus = racine / "corpus.json"
            bruts = racine / "bruts.json"
            corpus.write_text(
                json.dumps({"items": [{"id": "a", "abstract": "du corpus"}]}),
                encoding="utf-8",
            )
            bruts.write_text(
                json.dumps([{"id": "b", "abstract": "de la collecte"}]),
                encoding="utf-8",
            )

            with mock.patch.object(regenerer_flux, "CORPUS", corpus), \
                    mock.patch.object(regenerer_flux, "CANDIDATS_BRUTS", bruts),                     mock.patch.object(
                        regenerer_flux, "ABSTRACTS_RATTRAPAGE", racine / "absent.json"
                    ):
                abstracts = regenerer_flux.charger_abstracts()

            self.assertEqual(
                abstracts, {"a": "du corpus", "b": "de la collecte"}
            )

    def test_le_corpus_fige_prime_sur_la_collecte(self):
        # Le francais publie a ete redige depuis l'abstract fige. Prendre
        # celui de la collecte pour l'anglais ferait diverger les deux
        # langues d'un meme item sans que rien ne le signale.
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            corpus = racine / "corpus.json"
            bruts = racine / "bruts.json"
            corpus.write_text(
                json.dumps({"items": [{"id": "a", "abstract": "fige"}]}),
                encoding="utf-8",
            )
            bruts.write_text(
                json.dumps([{"id": "a", "abstract": "recollecte"}]),
                encoding="utf-8",
            )

            with mock.patch.object(regenerer_flux, "CORPUS", corpus), \
                    mock.patch.object(regenerer_flux, "CANDIDATS_BRUTS", bruts),                     mock.patch.object(
                        regenerer_flux, "ABSTRACTS_RATTRAPAGE", racine / "absent.json"
                    ):
                abstracts = regenerer_flux.charger_abstracts()

            self.assertEqual(abstracts["a"], "fige")

    def test_ignore_une_source_absente(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            corpus = racine / "corpus.json"
            corpus.write_text(
                json.dumps({"items": [{"id": "a", "abstract": "seul"}]}),
                encoding="utf-8",
            )

            with mock.patch.object(regenerer_flux, "CORPUS", corpus), \
                    mock.patch.object(
                        regenerer_flux, "CANDIDATS_BRUTS", racine / "absent.json"
                    ),                     mock.patch.object(
                        regenerer_flux, "ABSTRACTS_RATTRAPAGE", racine / "absent.json"
                    ):
                abstracts = regenerer_flux.charger_abstracts()

            self.assertEqual(abstracts, {"a": "seul"})


    def test_le_rattrapage_ne_supplante_pas_les_sources_d_origine(self):
        # Les abstracts retelecharges par collecter_abstracts_manquants
        # comblent les trous, ils ne remplacent pas celui qui a servi a
        # rediger le francais publie.
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            corpus = racine / "corpus.json"
            rattrapage = racine / "rattrapage.json"
            corpus.write_text(
                json.dumps({"items": [{"id": "a", "abstract": "fige"}]}),
                encoding="utf-8",
            )
            rattrapage.write_text(
                json.dumps([
                    {"id": "a", "abstract": "retelecharge"},
                    {"id": "b", "abstract": "trou comble"},
                ]),
                encoding="utf-8",
            )

            with mock.patch.object(regenerer_flux, "CORPUS", corpus),                     mock.patch.object(
                        regenerer_flux, "CANDIDATS_BRUTS", racine / "absent.json"
                    ),                     mock.patch.object(
                        regenerer_flux, "ABSTRACTS_RATTRAPAGE", rattrapage
                    ):
                abstracts = regenerer_flux.charger_abstracts()

            self.assertEqual(abstracts, {"a": "fige", "b": "trou comble"})


class TrierPourRattrapageTests(unittest.TestCase):
    def test_separe_les_trois_cas(self):
        flux = [
            {"id": "complet", "resume_en": "en", "angle_eco_en": "en"},
            {"id": "a_faire"},
            {"id": "sans_abstract"},
            # Un champ anglais sur deux ne suffit pas : l'item retourne dans
            # le lot a rediger, et ecrire_flux_anglais refusera de l'ecraser.
            {"id": "a_faire_partiel", "resume_en": "en"},
        ]
        abstracts = {"a_faire": "texte", "a_faire_partiel": "texte"}

        a_rediger, complets, sans_abstract = regenerer_flux.trier_pour_rattrapage(
            flux, abstracts
        )

        self.assertEqual([e["id"] for e in a_rediger], ["a_faire", "a_faire_partiel"])
        self.assertEqual([e["id"] for e in complets], ["complet"])
        self.assertEqual([e["id"] for e in sans_abstract], ["sans_abstract"])


class EstimerCoutTests(unittest.TestCase):
    def test_compte_deux_champs_et_deux_essais_par_item(self):
        a_rediger = [{"id": "a"}, {"id": "b"}]
        abstracts = {"a": "x" * 100, "b": "y" * 100}

        estimation = regenerer_flux.estimer_cout(a_rediger, abstracts)

        self.assertEqual(estimation["items"], 2)
        self.assertEqual(estimation["appels_min"], 4)
        self.assertEqual(estimation["appels_max"], 8)

    def test_plafonne_l_abstract_a_ce_que_le_prompt_en_reprend(self):
        # curate.construire_prompt_resume_en tronque a 1500 caracteres. Une
        # estimation qui compterait l'abstract entier annoncerait un cout
        # plusieurs fois trop eleve pour les articles longs.
        court = regenerer_flux.estimer_cout(
            [{"id": "a"}], {"a": "x" * regenerer_flux.ABSTRACT_MAX_DANS_PROMPT}
        )
        long = regenerer_flux.estimer_cout([{"id": "a"}], {"a": "x" * 40000})

        self.assertEqual(
            court["tokens_entree_max"], long["tokens_entree_max"]
        )

    def test_lot_vide_ne_coute_rien(self):
        estimation = regenerer_flux.estimer_cout([], {})

        self.assertEqual(estimation["appels_max"], 0)
        self.assertEqual(estimation["dollars_repli_max"], 0.0)


class EcrireFluxAnglaisTests(unittest.TestCase):
    def setUp(self):
        # ecrire_flux_anglais reinjecte desormais le JSON-LD via
        # publish.injecter_jsonld_flux, qui ecrit dans publish.FRONTIERE_INDEX
        # par defaut. Sans ce mock, chaque test ecrirait dans le vrai
        # frontiere/index.html du depot.
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        index = Path(dossier.name) / "index.html"
        index.write_text(GABARIT_FRONTIERE_INDEX, encoding="utf-8")
        # Le JSON-LD est reinjecte dans les deux pages depuis qu'elles servent
        # le meme flux : les deux chemins doivent etre detournes, pas seulement
        # le francais, sinon le vrai en/frontier/index.html du depot recoit les
        # entrees de test.
        index_en = Path(dossier.name) / "index-en.html"
        index_en.write_text(GABARIT_FRONTIERE_INDEX, encoding="utf-8")
        for nom, valeur in (("FRONTIERE_INDEX", index), ("FRONTIER_INDEX_EN", index_en)):
            patcheur = mock.patch.object(publish, nom, valeur)
            patcheur.start()
            self.addCleanup(patcheur.stop)
        self.index_frontiere = index
        self.index_frontier_en = index_en

    def _flux_temporaire(self, contenu):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        chemin = Path(dossier.name) / "flux.json"
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        return chemin

    def test_ajoute_les_champs_anglais_sans_toucher_au_francais(self):
        chemin = self._flux_temporaire([
            {
                "id": "a", "titre": "Titre", "url": "https://x.example/a",
                "resume_fr": "francais", "angle_eco": "angle",
            }
        ])
        releve = [{
            "id": "a",
            "titre": "A",
            "etat": "valide",
            "apres": {"resume_en": "English.", "angle_eco_en": "Angle."},
        }]

        with mock.patch.object(regenerer_flux, "FLUX", chemin):
            flux = json.loads(chemin.read_text(encoding="utf-8"))
            nb = regenerer_flux.ecrire_flux_anglais(flux, releve)

        ecrit = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(nb, 1)
        self.assertEqual(ecrit[0]["resume_fr"], "francais")
        self.assertEqual(ecrit[0]["angle_eco"], "angle")
        self.assertEqual(ecrit[0]["resume_en"], "English.")
        self.assertEqual(ecrit[0]["angle_eco_en"], "Angle.")
        # Preuve que le mock du sandbox est bien celui utilise : le JSON-LD
        # reinjecte porte l'item du test, pas celui du vrai site.
        self.assertIn('"headline": "Titre"', self.index_frontiere.read_text(encoding="utf-8"))

    def test_n_ecrase_pas_un_item_devenu_bilingue_entre_temps(self):
        # Le pipeline a pu publier l'anglais de cet item pendant que le lot
        # de rattrapage attendait sa relecture. Son texte vient de l'abstract
        # courant : l'ecraser annulerait une publication en silence.
        chemin = self._flux_temporaire([
            {
                "id": "a", "titre": "A", "url": "https://x.example/a",
                "resume_fr": "f", "resume_en": "publie par le pipeline",
            }
        ])
        releve = [{
            "id": "a",
            "titre": "A",
            "etat": "valide",
            "apres": {"resume_en": "du rattrapage", "angle_eco_en": "angle"},
        }]

        with mock.patch.object(regenerer_flux, "FLUX", chemin):
            flux = json.loads(chemin.read_text(encoding="utf-8"))
            nb = regenerer_flux.ecrire_flux_anglais(flux, releve)

        ecrit = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(nb, 0)
        self.assertEqual(ecrit[0]["resume_en"], "publie par le pipeline")

    def test_ignore_un_item_rejete(self):
        chemin = self._flux_temporaire([
            {
                "id": "a", "titre": "Titre", "url": "https://x.example/a",
                "resume_fr": "francais",
            }
        ])
        releve = [{
            "id": "a",
            "titre": "A",
            "etat": "rejete",
            "apres": {"resume_en": "", "angle_eco_en": ""},
        }]

        with mock.patch.object(regenerer_flux, "FLUX", chemin):
            flux = json.loads(chemin.read_text(encoding="utf-8"))
            nb = regenerer_flux.ecrire_flux_anglais(flux, releve)

        ecrit = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(nb, 0)
        self.assertNotIn("resume_en", ecrit[0])


class BudgetAnglaisTests(unittest.TestCase):
    def test_le_cout_par_item_du_rattrapage_est_celui_des_deux_champs(self):
        # Avec le cout d'une execution complete, un budget de 16 laisserait
        # passer 2 items au lieu de 4 : le rattrapage s'arreterait avec la
        # moitie du budget inutilisee.
        with mock.patch.object(curate, "BUDGET_APPELS", 16), \
                mock.patch.object(curate, "_appels_effectues", 8):
            self.assertFalse(
                curate.budget_epuise(curate.APPELS_MAX_ANGLAIS_SEUL)
            )

    def test_s_arrete_quand_il_ne_reste_pas_de_quoi_faire_un_item(self):
        with mock.patch.object(curate, "BUDGET_APPELS", 16), \
                mock.patch.object(curate, "_appels_effectues", 13):
            self.assertTrue(
                curate.budget_epuise(curate.APPELS_MAX_ANGLAIS_SEUL)
            )

    def test_sans_budget_declare_rien_n_arrete_le_lot(self):
        with mock.patch.object(curate, "BUDGET_APPELS", 0), \
                mock.patch.object(curate, "_appels_effectues", 1000):
            self.assertFalse(
                curate.budget_epuise(curate.APPELS_MAX_ANGLAIS_SEUL)
            )


if __name__ == "__main__":
    unittest.main()
