"""Tests de pipeline.verifier_html.

Les deux premiers cas rejouent la regression reelle du 2026-08-11 sur
parcours.html : une balise <article> ouverte deux fois, et un </ul> laisse
derriere apres un remaniement de liste.

    python -m unittest pipeline.test_verifier_html
"""

import unittest

from pipeline import verifier_html


def anomalies(fragment):
    return verifier_html.anomalies_de_balises(fragment)


class BalisesTests(unittest.TestCase):
    def test_page_saine_ne_signale_rien(self):
        self.assertEqual(anomalies("<div><p>texte</p><img src='a.jpg'><br></div>"), [])

    def test_balise_ouverte_deux_fois(self):
        # Regression du 2026-08-11 : <article> duplique dans parcours.html.
        resultat = anomalies("<div>\n<article>\n<article>\n<h3>Titre</h3>\n</article>\n</div>")
        self.assertTrue(resultat)
        self.assertIn("<article> (ligne 2) n'est pas fermee", " ".join(m for _, m in resultat))

    def test_fermeture_orpheline(self):
        # Regression du 2026-08-11 : </ul> restant apres remaniement du bloc UdeS.
        resultat = anomalies("<article>\n<p>texte</p>\n</ul>\n</article>")
        self.assertEqual([m for _, m in resultat], ["</ul> ferme une balise jamais ouverte"])

    def test_numero_de_ligne_signale(self):
        resultat = anomalies("<div>\n\n\n</ul>\n</div>")
        self.assertEqual(resultat[0][0], 4)

    def test_imbrication_croisee(self):
        self.assertTrue(anomalies("<div><section></div></section>"))

    def test_balises_orphelines_ignorees(self):
        self.assertEqual(anomalies("<p><br><hr><input name='a'></p>"), [])

    def test_autofermantes_ignorees(self):
        self.assertEqual(anomalies("<svg><path d='M0 0'/></svg>"), [])

    def test_commentaires_et_scripts_ignores(self):
        contenu = "<div><!-- <article> --><script>if (a<b) {}</script></div>"
        self.assertEqual(anomalies(contenu), [])


class TypographieTests(unittest.TestCase):
    def test_apostrophe_courbe_signalee(self):
        resultat = verifier_html.anomalies_de_typographie("<p>d’un modele</p>")
        self.assertEqual([m for _, m in resultat], ["apostrophe courbe, le site utilise l'apostrophe droite"])

    def test_apostrophe_droite_acceptee(self):
        self.assertEqual(verifier_html.anomalies_de_typographie("<p>d'un modele</p>"), [])

    def test_esperluette_nue_signalee(self):
        resultat = verifier_html.anomalies_de_typographie("<li>coursework & exams</li>")
        self.assertEqual([m for _, m in resultat], ["esperluette nue, ecrire &amp;"])

    def test_entites_acceptees(self):
        contenu = "<li>coursework &amp; exams &#233; &#x27;</li>"
        self.assertEqual(verifier_html.anomalies_de_typographie(contenu), [])


class SiteTests(unittest.TestCase):
    def test_toutes_les_pages_publiees_sont_valides(self):
        pages = verifier_html.pages_du_site()
        self.assertTrue(pages, "aucune page HTML trouvee")
        for page in pages:
            with self.subTest(page=page.name):
                self.assertEqual(verifier_html.verifier(page), [])


class HookTests(unittest.TestCase):
    def test_hook_present_dans_githooks_pas_dans_pipeline(self):
        racine = verifier_html.RACINE
        self.assertTrue((racine / ".githooks" / "pre-commit").exists())
        self.assertFalse((racine / "pipeline" / "pre-commit").exists())


if __name__ == "__main__":
    unittest.main()
