import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import verifier_bilinguisme_flux as verif


def _item(identifiant, resume_en="", angle_eco_en=""):
    return {
        "id": identifiant,
        "titre": identifiant,
        "resume_fr": "fr",
        "resume_en": resume_en,
        "angle_eco_en": angle_eco_en,
    }


class ItemsEnRepliTests(unittest.TestCase):
    def test_un_champ_anglais_sur_deux_ne_suffit_pas(self):
        # La page anglaise sert le francais des que resume_en manque : un
        # angle anglais seul ne sort pas l'item du repli.
        items = [
            _item("complet", "resume", "angle"),
            _item("angle_seul", "", "angle"),
            _item("resume_seul", "resume", ""),
            _item("vide"),
        ]
        self.assertEqual(
            [i["id"] for i in verif.items_en_repli(items)],
            ["angle_seul", "resume_seul", "vide"],
        )


class MainTests(unittest.TestCase):
    def _executer(self, items):
        with tempfile.TemporaryDirectory() as dossier:
            flux = Path(dossier) / "flux.json"
            flux.write_text(json.dumps(items), encoding="utf-8")
            with mock.patch.object(verif, "FLUX", flux):
                return verif.main()

    def test_accepte_un_item_isole_sans_source_anglaise(self):
        items = [_item(f"i{n}", "resume", "angle") for n in range(20)]
        items.append(_item("irrecuperable"))
        self.assertEqual(self._executer(items), 0)

    def test_echoue_quand_le_repli_devient_general(self):
        items = [_item(f"i{n}", "resume", "angle") for n in range(5)]
        items += [_item(f"vide{n}") for n in range(5)]
        self.assertEqual(self._executer(items), 1)

    def test_flux_absent_ne_fait_pas_echouer(self):
        with tempfile.TemporaryDirectory() as dossier:
            with mock.patch.object(verif, "FLUX", Path(dossier) / "absent.json"):
                self.assertEqual(verif.main(), 0)
