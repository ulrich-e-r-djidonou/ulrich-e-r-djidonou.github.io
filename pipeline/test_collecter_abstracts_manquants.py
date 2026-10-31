"""Tests de l'aiguillage par domaine de pipeline.collecter_abstracts_manquants.

Alertes CodeQL py/incomplete-url-substring-sanitization (31 oct. 2026) : un
test par sous-chaine (`"arxiv.org" in url`) envoyait vers la recolte arXiv
toute URL qui contenait ce texte, y compris dans sa requete ou dans un
domaine tiers.

    python -m unittest pipeline.test_collecter_abstracts_manquants
"""

import unittest

from pipeline.collecter_abstracts_manquants import _domaine


class DomaineTests(unittest.TestCase):
    def test_domaine_exact_et_sous_domaine(self):
        self.assertTrue(_domaine("https://arxiv.org/abs/2601.00001", "arxiv.org"))
        self.assertTrue(_domaine("https://export.arxiv.org/abs/2601.00001", "arxiv.org"))
        self.assertTrue(_domaine("https://WWW.NBER.ORG/papers/w33000", "nber.org"))

    def test_domaine_dans_la_requete_refuse(self):
        self.assertFalse(_domaine("https://exemple.com/?u=arxiv.org", "arxiv.org"))

    def test_domaine_prefixe_d_un_tiers_refuse(self):
        self.assertFalse(_domaine("https://arxiv.org.exemple.com/abs/1", "arxiv.org"))
        self.assertFalse(_domaine("https://faux-arxiv.org/abs/1", "arxiv.org"))

    def test_url_sans_hote(self):
        self.assertFalse(_domaine("pas une url", "doi.org"))


if __name__ == "__main__":
    unittest.main()
