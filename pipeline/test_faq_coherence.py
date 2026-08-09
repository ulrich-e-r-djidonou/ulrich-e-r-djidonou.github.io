"""Verifie que la FAQ visible d'index.html et le bloc FAQPage (JSON-LD) disent
la meme chose, dans le meme ordre.

Un moteur de recherche affiche le contenu du bloc FAQPage tel quel dans les
resultats enrichis, pas le HTML visible : s'ils divergent (question ajoutee
d'un seul cote, reponse modifiee dans un seul des deux endroits), le
resultat enrichi montre un contenu que le visiteur ne retrouve pas sur la
page, ce qui est sanctionne par Google et trompeur pour le lecteur. C'est le
controle qui a manque lors de la revue manuelle du 2026-08-08 (voir
docs/decisions.md) : refait ici pour ne plus dependre d'une relecture a l'oeil.

    python -m pipeline.test_faq_coherence
    pytest pipeline/test_faq_coherence.py
"""

import json
import re
import unittest
from pathlib import Path

RACINE = Path(__file__).parent.parent
INDEX = RACINE / "index.html"

MOTIF_BLOC_JSONLD = re.compile(
    r'<script type="application/ld\+json"[^>]*>\s*(.*?)\s*</script>', re.DOTALL
)
MOTIF_LISTE_FAQ = re.compile(
    r'<div class="faq-list">(.*?)</div>\s*</section>', re.DOTALL
)
MOTIF_DETAILS = re.compile(
    r"<details>\s*<summary>(.*?)</summary>(.*?)</details>", re.DOTALL
)
MOTIF_PARAGRAPHE = re.compile(r"<p>(.*?)</p>", re.DOTALL)


def texte_sans_balises(fragment):
    sans_balises = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", sans_balises).strip()


def lire_faqpage_json(chemin=INDEX):
    """Renvoie la liste (question, reponse) du bloc FAQPage, dans son ordre."""
    contenu = chemin.read_text(encoding="utf-8")
    for bloc in MOTIF_BLOC_JSONLD.findall(contenu):
        donnees = json.loads(bloc)
        if donnees.get("@type") == "FAQPage":
            return [
                (question["name"], question["acceptedAnswer"]["text"])
                for question in donnees["mainEntity"]
            ]
    raise AssertionError(f"{chemin.name} : aucun bloc FAQPage trouve")


def lire_faq_visible(chemin=INDEX):
    """Renvoie la liste (question, reponse) affichee dans .faq-list, dans
    l'ordre d'affichage. Les balises (liens compris) sont retirees pour ne
    garder que le texte lu par le visiteur."""
    contenu = chemin.read_text(encoding="utf-8")
    correspondance = MOTIF_LISTE_FAQ.search(contenu)
    if not correspondance:
        raise AssertionError(f"{chemin.name} : bloc .faq-list introuvable")
    resultat = []
    for resume, corps in MOTIF_DETAILS.findall(correspondance.group(1)):
        question = texte_sans_balises(resume)
        reponse = " ".join(
            texte_sans_balises(paragraphe)
            for paragraphe in MOTIF_PARAGRAPHE.findall(corps)
        )
        resultat.append((question, reponse))
    return resultat


class FaqCoherenceTests(unittest.TestCase):
    def test_meme_nombre_de_questions(self):
        self.assertEqual(len(lire_faq_visible()), len(lire_faqpage_json()))

    def test_questions_identiques_et_dans_le_meme_ordre(self):
        visible = [question for question, _ in lire_faq_visible()]
        json_ld = [question for question, _ in lire_faqpage_json()]
        self.assertEqual(visible, json_ld)

    def test_reponses_identiques(self):
        visible = lire_faq_visible()
        json_ld = dict(lire_faqpage_json())
        for question, reponse_visible in visible:
            with self.subTest(question=question):
                self.assertIn(question, json_ld)
                self.assertEqual(reponse_visible, json_ld[question])


if __name__ == "__main__":
    unittest.main()
