import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import rendre_notification_publication as notif


class ItemsPubliesTests(unittest.TestCase):
    def test_ecarte_un_candidat_redige_mais_non_publie(self):
        # Un candidat peut etre redige puis archive (score trop bas) ou
        # ecarte (lien mort). Le notifier annoncerait une publication qui
        # n'a pas eu lieu.
        cures = [{"id": "publie"}, {"id": "archive"}]
        flux = [{"id": "publie", "titre": "T", "url": "u"}]
        self.assertEqual(
            [i["id"] for i in notif.items_publies(cures, flux)], ["publie"]
        )

    def test_prend_la_version_du_flux_et_non_celle_du_candidat(self):
        # publish.py peut retoucher une entree avant de l'ecrire. La
        # notification doit refleter ce qui est en ligne.
        cures = [{"id": "a", "titre": "avant"}]
        flux = [{"id": "a", "titre": "apres", "url": "u"}]
        self.assertEqual(notif.items_publies(cures, flux)[0]["titre"], "apres")


class MainTests(unittest.TestCase):
    def _executer(self, cures, flux, sortie):
        with mock.patch.object(notif, "CURES", cures), \
                mock.patch.object(notif, "FLUX", flux), \
                mock.patch.object(notif, "SORTIE", sortie):
            return notif.main()

    def test_n_ecrit_rien_quand_il_n_y_a_rien_de_neuf(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            cures = racine / "cures.json"
            flux = racine / "flux.json"
            sortie = racine / "sortie.md"
            cures.write_text("[]", encoding="utf-8")
            flux.write_text(json.dumps([{"id": "a"}]), encoding="utf-8")

            self.assertEqual(self._executer(cures, flux, sortie), 0)
            self.assertFalse(sortie.exists())

    def test_efface_le_rapport_de_la_veille_quand_rien_n_est_publie(self):
        # Sans cet effacement, le workflow rouvrirait une issue avec le
        # contenu de l'execution precedente.
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            cures = racine / "cures.json"
            flux = racine / "flux.json"
            sortie = racine / "sortie.md"
            cures.write_text("[]", encoding="utf-8")
            flux.write_text("[]", encoding="utf-8")
            sortie.write_text("# la veille", encoding="utf-8")

            self.assertEqual(self._executer(cures, flux, sortie), 0)
            self.assertFalse(sortie.exists())

    def test_ecrit_titre_lien_et_pages_du_site(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            cures = racine / "cures.json"
            flux = racine / "flux.json"
            sortie = racine / "sortie.md"
            cures.write_text(json.dumps([{"id": "a"}]), encoding="utf-8")
            flux.write_text(
                json.dumps([{
                    "id": "a",
                    "titre": "Un papier",
                    "url": "https://exemple.org/a",
                    "source": "NBER",
                    "date_publication": "2026-08-24",
                    "resume_fr": "Deux phrases.",
                    "angle_eco": "Un mecanisme.",
                }]),
                encoding="utf-8",
            )

            self.assertEqual(self._executer(cures, flux, sortie), 0)
            texte = sortie.read_text(encoding="utf-8")
            self.assertIn("[Un papier](https://exemple.org/a)", texte)
            self.assertIn("Deux phrases.", texte)
            self.assertIn("Un mecanisme.", texte)
            self.assertIn(notif.PAGE, texte)
            self.assertIn(notif.PAGE_EN, texte)

    def test_fichiers_absents_ne_font_pas_echouer(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            self.assertEqual(
                self._executer(
                    racine / "absent1.json",
                    racine / "absent2.json",
                    racine / "sortie.md",
                ),
                0,
            )
