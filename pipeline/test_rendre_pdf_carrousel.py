import tempfile
import unittest
from pathlib import Path

from pipeline import rendre_pdf_carrousel as pdf


PLAN = """# Carrousel La Frontiere, 2026-08-29

Statut : PLAN A VALIDER.

---

## Diapositive 1, couverture

**Deux papiers, une meme lecon.**

La Frontiere, veille du 29 aout 2026

---

## Diapositive 2, le signal de la semaine

**Manipulation-Robust Prediction**
Bjorkegren, Blumenstock & Knight, American Economic Review, septembre 2026

Un algorithme de ciblage devient public.

Source : https://doi.org/10.1257/aer.20241087

---

## Diapositive 3, question de cloture

Qu'est-ce qui vous frappe davantage ?

---

# Texte du post

Ce paragraphe accompagne la publication, pas le carrousel.

# Sources

- Manipulation-Robust Prediction. https://doi.org/10.1257/aer.20241087
"""


class DecouperTests(unittest.TestCase):
    def test_retient_une_diapositive_par_titre_numerote(self):
        self.assertEqual(len(pdf.decouper(PLAN)), 3)

    def test_ecarte_les_sections_de_relecture(self):
        # Le texte du post et les sources servent a publier, pas a illustrer.
        texte = " ".join(
            " ".join(d["lignes"]) for d in pdf.decouper(PLAN)
        )
        self.assertNotIn("accompagne la publication", texte)

    def test_conserve_le_role_de_chaque_diapositive(self):
        roles = [d["role"] for d in pdf.decouper(PLAN)]
        self.assertEqual(roles[1], "le signal de la semaine")


class EchelleTests(unittest.TestCase):
    def test_laisse_un_texte_court_a_pleine_taille(self):
        self.assertEqual(pdf.echelle(["a" * 100]), 1.0)

    def test_reduit_un_texte_dense(self):
        # Un cadre carre ne s'allonge pas : sans reduction, Chrome coupe le
        # bas de la diapositive et le defaut ne se voit qu'apres publication.
        self.assertLess(pdf.echelle(["a" * 600]), 1.0)

    def test_reduit_davantage_a_mesure_que_le_volume_monte(self):
        self.assertLess(pdf.echelle(["a" * 700]), pdf.echelle(["a" * 500]))


class RendreHtmlTests(unittest.TestCase):
    def test_remplace_les_etiquettes_de_production_par_du_contenu(self):
        # « couverture » et « question de cloture » nomment le role dans le
        # plan : les afficher ferait passer une note de travail dans l'image.
        html = pdf.rendre_html(pdf.decouper(PLAN))
        self.assertNotIn(">couverture<", html)
        self.assertNotIn(">question de cloture<", html)
        self.assertIn("La Frontière", html)

    def test_deplace_la_source_vers_le_pied_de_diapositive(self):
        html = pdf.rendre_html(pdf.decouper(PLAN))
        self.assertNotIn("Source :", html)
        self.assertIn("doi.org/10.1257/aer.20241087", html)

    def test_pagine_une_diapositive_par_page(self):
        html = pdf.rendre_html(pdf.decouper(PLAN))
        self.assertEqual(html.count('class="slide"'), 3)

    def test_impose_le_format_carre(self):
        html = pdf.rendre_html(pdf.decouper(PLAN))
        self.assertIn("size: 1080px 1080px", html)

    def test_echappe_le_contenu_avant_de_l_injecter(self):
        diapositives = [{"role": "essai", "lignes": ["<script>alerte</script>"]}]
        self.assertNotIn("<script>alerte", pdf.rendre_html(diapositives))


class GardeTests(unittest.TestCase):
    def test_refuse_un_plan_non_complete(self):
        # Sans cette garde, le PDF sortirait avec « [A COMPLETER] » a la
        # place de l'angle, et le defaut se verrait sur LinkedIn.
        with tempfile.TemporaryDirectory() as dossier:
            plan = Path(dossier) / "plan.md"
            plan.write_text(
                "## Diapositive 1, couverture\n\n[A COMPLETER] : l'accroche.\n",
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit) as leve:
                pdf.main([str(plan)])
            self.assertIn("A COMPLETER", str(leve.exception))

    def test_refuse_un_plan_introuvable(self):
        with self.assertRaises(SystemExit):
            pdf.main(["carrousels/inexistant.md"])


if __name__ == "__main__":
    unittest.main()
