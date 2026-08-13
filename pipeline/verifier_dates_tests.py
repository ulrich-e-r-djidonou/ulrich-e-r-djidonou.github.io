"""Detecte les dates litterales combinees a une fenetre glissante dans les tests.

Le 13 aout 2026, test_axe_depot_utilise_created_pour_la_date a echoue en CI
sans qu'aucun code applicatif n'ait bouge. Cause : une date de creation figee
au 30 juillet 2026, verifiee contre une fenetre de 14 jours. Au 13 aout, elle
en etait sortie. Le test dormait depuis sa creation et s'est declenche tout
seul, un mois plus tard, sur un commit sans rapport.

Ce n'est pas un incident isole mais une classe de bug : tout test qui combine
une date litterale et une notion de fenetre glissante (fenetre_jours,
dans_fenetre, un seuil de dormance) finit par se declencher de lui-meme, au
gre du calendrier plutot que d'une regression reelle.

Une date litterale n'est pas toujours le probleme : DateCrossrefTests dans
test_collect.py verifie un parsing de date, la valeur litterale y est
precisement le sujet du test, sans qu'aucune fenetre n'intervienne. La regle
retenue est volontairement etroite pour ne pas les signaler : seule la
combinaison d'une date litterale ET d'un indice de fenetre glissante, dans le
meme test, est rapportee.

Bloquant, comme verifier_html et verifier_csp : un test qui se declenchera
tout seul dans quelques semaines est un defaut du depot au moment ou on
l'ecrit, pas une simple information a surveiller.

    python -m pipeline.verifier_dates_tests
"""

import ast
import re
import sys
from pathlib import Path

RACINE = Path(__file__).parent.parent

# Une annee a 4 chiffres commencant par 20, suivie d'un mois plausible :
# couvre date(2026, 7, 30), datetime(2026, 7, 30, ...), et les tuples
# [2026, 7, 30] ou [[2026, 7, 30]] utilises pour simuler des reponses
# Crossref (date-parts). Le mois est bref (1-2 chiffres) pour ne pas
# confondre avec un ISSN ou un DOI, qui ne s'ecrivent jamais sous cette
# forme dans le code des tests.
MOTIF_DATE_LITTERALE = re.compile(
    r"(?:date|datetime)\(\s*20\d{2}\s*,\s*\d{1,2}"
    r"|\[\s*20\d{2}\s*,\s*\d{1,2}"
    r"|\b20\d{2}-\d{2}-\d{2}\b"
)

# Indices qu'un test raisonne sur une fenetre glissante plutot que sur une
# date fixe. « fenetre_jours » couvre les sources RSS/Crossref, les deux
# autres la sonde de fraicheur.
INDICES_FENETRE = ("fenetre_jours", "dans_fenetre", "SEUIL_DORMANCE_JOURS")

# Ce module se signalerait lui-meme : ses propres tests contiennent, dans des
# chaines de caracteres, des extraits de code fabriques pour declencher ou
# non la detection (voir test_verifier_dates_tests.py). Le motif ne distingue
# pas du code reel une chaine qui en a la forme ; l'exclure est plus simple
# que d'analyser recursivement le contenu des chaines.
FICHIERS_EXCLUS = {"test_verifier_dates_tests.py"}


def tests_a_risque(code):
    """Fonctions test_* combinant une date litterale et une fenetre glissante.

    Pure : prend du code source en texte, ne touche ni au disque ni au
    reseau. Renvoie une liste de (nom_fonction, ligne).
    """
    trouvailles = []
    try:
        arbre = ast.parse(code)
    except SyntaxError:
        return trouvailles

    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.FunctionDef) and noeud.name.startswith("test_")):
            continue
        source_fonction = ast.get_source_segment(code, noeud) or ""
        if MOTIF_DATE_LITTERALE.search(source_fonction) and any(
            indice in source_fonction for indice in INDICES_FENETRE
        ):
            trouvailles.append((noeud.name, noeud.lineno))

    return trouvailles


def fichiers_de_tests(racine=RACINE):
    fichiers = sorted(racine.glob("pipeline/test_*.py")) + sorted(
        racine.glob("pipeline/benchmark/test_*.py")
    )
    return [f for f in fichiers if f.name not in FICHIERS_EXCLUS]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    rapport_seul = "--rapport-seul" in argv
    fichiers = [Path(a) for a in argv if a != "--rapport-seul"] or fichiers_de_tests()

    anomalies = []
    for fichier in fichiers:
        code = fichier.read_text(encoding="utf-8")
        for nom_test, ligne in tests_a_risque(code):
            anomalies.append((fichier, nom_test, ligne))

    if not anomalies:
        print(f"Aucune date litterale a risque : {len(fichiers)} fichier(s) de tests verifies.")
        return 0

    print(f"{len(anomalies)} test(s) combinent une date litterale et une fenetre glissante :\n")
    for fichier, nom_test, ligne in anomalies:
        relatif = fichier.relative_to(RACINE) if fichier.is_absolute() else fichier
        print(f"  {relatif}:{ligne} : {nom_test}")
    print(
        "\nCe test finira par echouer tout seul quand la date sortira de la "
        "fenetre. Remplacer la date litterale par une date relative a "
        "aujourd'hui (date.today() - timedelta(days=...))."
    )

    return 0 if rapport_seul else 1


if __name__ == "__main__":
    raise SystemExit(main())
