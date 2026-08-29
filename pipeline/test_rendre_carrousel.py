import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import rendre_carrousel as carrousel


SIGNAL = {
    "id": "s",
    "titre": "Manipulation-Robust Prediction",
    "url": "https://doi.org/10.1257/aer.20241087",
    "source": "American Economic Review",
    "date_publication": "2026-09-01",
    "auteurs": "Bjorkegren, Blumenstock, Knight",
    "resume_fr": "Des regles de decision robustes a la manipulation.",
    "angle_eco": "La prevision cesse d'etre exterieure au systeme qu'elle mesure.",
    "signal": True,
    "llm": "gemini-3.6-flash",
}

AUTRE = {
    "id": "a",
    "titre": "Pricing with Algorithms",
    "url": "https://doi.org/10.1257/aeri.20240436",
    "source": "AER: Insights",
    "date_publication": "2026-09-01",
    "auteurs": "Lamba, Zhuk",
    "resume_fr": "Des equilibres supraconcurrentiels sur toute grille finie.",
    "angle_eco": "La collusion tacite sans communication interroge l'antitrust.",
    "signal": False,
    "llm": "claude-haiku-4-5",
}


class SeparerSignalTests(unittest.TestCase):
    def test_isole_le_signal_des_autres_items(self):
        signal, autres = carrousel.separer_signal([AUTRE, SIGNAL])
        self.assertEqual(signal["id"], "s")
        self.assertEqual([i["id"] for i in autres], ["a"])

    def test_rend_none_quand_aucun_item_ne_porte_le_signal(self):
        # Une mise a jour de routine ne merite pas une demande de validation.
        signal, autres = carrousel.separer_signal([AUTRE])
        self.assertIsNone(signal)
        self.assertEqual(len(autres), 1)


class VigilanceTests(unittest.TestCase):
    def test_repere_un_sujet_rapportable_a_l_employeur(self):
        item = dict(SIGNAL, titre="Child well-being and public transfers")
        self.assertIn("child", carrousel.mots_sensibles_reperes([item]))

    def test_ne_signale_rien_sur_un_lot_neutre(self):
        self.assertEqual(carrousel.mots_sensibles_reperes([SIGNAL, AUTRE]), [])

    def test_l_avertissement_apparait_dans_le_brouillon(self):
        item = dict(SIGNAL, resume_fr="Effets sur la protection de la jeunesse.")
        texte = carrousel.rendre([item], "2026-08-29", 68)
        self.assertIn("VIGILANCE", texte)

    def test_la_vigilance_n_empeche_pas_la_generation(self):
        # Un avertissement pour la relecture, pas une censure automatique.
        item = dict(SIGNAL, resume_fr="Effets sur la protection de la jeunesse.")
        texte = carrousel.rendre([item], "2026-08-29", 68)
        self.assertIn(item["titre"], texte)


class RendreTests(unittest.TestCase):
    def test_laisse_l_angle_editorial_a_completer(self):
        # Le script met en forme, il ne formule pas l'avis : un carrousel qui
        # resume des resumes n'apporte rien qu'un abstract ne donne deja.
        texte = carrousel.rendre([SIGNAL, AUTRE], "2026-08-29", 68)
        self.assertGreaterEqual(texte.count(carrousel.A_COMPLETER), 3)

    def test_nomme_les_modeles_ayant_redige_les_textes(self):
        texte = carrousel.rendre([SIGNAL, AUTRE], "2026-08-29", 68)
        self.assertIn("gemini-3.6-flash", texte)
        self.assertIn("claude-haiku-4-5", texte)

    def test_reclame_une_verification_a_la_source(self):
        texte = carrousel.rendre([SIGNAL], "2026-08-29", 68)
        self.assertIn("A verifier avant publication", texte)

    def test_liste_chaque_item_en_source_avec_son_lien(self):
        texte = carrousel.rendre([SIGNAL, AUTRE], "2026-08-29", 68)
        self.assertIn(SIGNAL["url"], texte)
        self.assertIn(AUTRE["url"], texte)

    def test_place_le_signal_avant_les_autres_items(self):
        texte = carrousel.rendre([AUTRE, SIGNAL], "2026-08-29", 68)
        self.assertLess(texte.index(SIGNAL["titre"]), texte.index(AUTRE["titre"]))

    def test_annonce_le_nombre_d_entrees_de_la_veille(self):
        self.assertIn("68 entrees", carrousel.rendre([SIGNAL], "2026-08-29", 68))

    def test_rappelle_que_rien_n_est_publie_sans_accord(self):
        self.assertIn("PLAN A VALIDER", carrousel.rendre([SIGNAL], "2026-08-29", 68))

    def test_omet_le_fil_commun_quand_le_signal_est_seul(self):
        # Sans second papier, il n'y a pas de fil a tracer.
        self.assertNotIn("le fil commun", carrousel.rendre([SIGNAL], "2026-08-29", 68))


class NePasEcraserTests(unittest.TestCase):
    def test_conserve_un_plan_deja_retravaille(self):
        # Deux executions peuvent tomber le meme jour. Reecrire le squelette
        # effacerait le travail editorial sans que rien ne le signale.
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            plan = racine / "2026-08-29-frontiere.md"
            plan.write_text("mon angle a moi", encoding="utf-8")
            with mock.patch.object(carrousel, "DOSSIER", racine), \
                 mock.patch.object(carrousel, "SORTIE", racine / "s.md"), \
                 mock.patch.object(carrousel, "SORTIE_TITRE", racine / "t.txt"), \
                 mock.patch.object(carrousel, "charger", lambda f, d: [SIGNAL]), \
                 mock.patch.object(carrousel, "items_publies", lambda c, f: [SIGNAL]):
                carrousel.main(date="2026-08-29")
            self.assertEqual(plan.read_text(encoding="utf-8"), "mon angle a moi")

    def test_l_issue_reprend_le_plan_conserve_et_non_le_squelette(self):
        # Ulrich doit relire ce qui est sur le disque, pas une version neuve.
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            (racine / "2026-08-29-frontiere.md").write_text("mon angle", encoding="utf-8")
            sortie = racine / "s.md"
            with mock.patch.object(carrousel, "DOSSIER", racine), \
                 mock.patch.object(carrousel, "SORTIE", sortie), \
                 mock.patch.object(carrousel, "SORTIE_TITRE", racine / "t.txt"), \
                 mock.patch.object(carrousel, "charger", lambda f, d: [SIGNAL]), \
                 mock.patch.object(carrousel, "items_publies", lambda c, f: [SIGNAL]):
                carrousel.main(date="2026-08-29")
            self.assertEqual(sortie.read_text(encoding="utf-8"), "mon angle")


class TitreTests(unittest.TestCase):
    def test_l_objet_du_courriel_dit_qu_une_validation_est_attendue(self):
        self.assertIn("a valider", carrousel.rendre_titre("2026-08-29"))


if __name__ == "__main__":
    unittest.main()
