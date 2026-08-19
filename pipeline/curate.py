"""Curation pour La Frontiere.

Lit pipeline/_candidats_bruts.json et pipeline/seen.json, calcule un score
heuristique et un resume extrait pour chaque candidat non deja vu, et ecrit
pipeline/_candidats_cures.json pour la selection principale et
pipeline/_candidats_archives.json pour les items sous le seuil.

Le score reste TOUJOURS heuristique (deterministe, auditable) : un LLM ne
sert jamais au tri, seulement a la redaction (resume + angle economiste),
et seulement sur les items deja retenus par le seuil.

La redaction est confiee a un modele, local ou distant selon FRONTIERE_LLM :
ollama pour un modele local, api pour tout service expose au format OpenAI.
Le fournisseur ne change que la redaction du resume et de l'angle, jamais la
selection. Chaque sortie est validee separement. Une sortie invalide est
relancee une fois, puis l'item n'est pas publie si le second essai echoue.
Aucun extrait anglais n'est publie en repli.

Pour le fournisseur api, un second point de terminaison de repli peut etre
configure (LLM_API_URL_REPLI et consorts, meme format OpenAI). Si le
fournisseur principal echoue apres ses propres tentatives (quota epuise,
panne), la redaction bascule dessus pour le reste de l'execution au lieu
d'echouer tout de suite. Le budget d'appels (LLM_BUDGET_APPELS) reste compte
une seule fois, tous fournisseurs confondus. Sans repli configure, le
comportement est inchange : une panne du fournisseur principal fait echouer
le run.

Deux echecs sont distingues, parce qu'ils n'appellent pas la meme reaction :
  - echec de validation : le modele a repondu, mal. L'item est marque vu et
    ne sera pas repeche. C'est la politique arretee.
  - service indisponible : ni le fournisseur principal ni son repli (s'il est
    configure) n'ont repondu. Rien n'est ecrit, aucun item n'est marque vu,
    le script sort en erreur. Une panne ne doit jamais consommer
    definitivement des articles.
"""

import json
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ICI = Path(__file__).parent
ENTREE = ICI / "_candidats_bruts.json"
SORTIE = ICI / "_candidats_cures.json"
SORTIE_ARCHIVE = ICI / "_candidats_archives.json"
SEEN = ICI / "seen.json"
# Committe (pas dans .gitignore) : verifier_sante.py doit retrouver
# l'historique d'une execution a l'autre, ce qu'un fichier ignore ne permet pas.
SANTE = ICI.parent / "frontiere" / "data" / "sante.json"
NB_EXECUTIONS_CONSERVEES = 12

# Deux fournisseurs possibles pour la redaction, choisis par FRONTIERE_LLM :
#   ollama : modele local, ce que fait la production aujourd'hui
#   api    : tout service expose au format OpenAI (DeepSeek, Gemini, autres)
# Le tri reste heuristique dans les deux cas : le fournisseur ne change que la
# redaction, jamais la selection.
FOURNISSEUR = os.environ.get("FRONTIERE_LLM", "")
LLM_ACTIF = FOURNISSEUR in ("ollama", "api")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = 60
PAUSE_AVANT_REPRISE = 2
# Les paliers gratuits limitent le debit. Quelques essais espaces valent mieux
# qu'un abandon : le lot est petit et ne tourne que trois fois par semaine.
TENTATIVES_API = 4
PAUSE_MAX_DEBIT = 65
# Saturation passagere du service, et non refus : le modele redevient
# disponible, mais rarement dans les deux secondes de la pause ordinaire.
CODES_SATURATION = (500, 502, 503, 504)

API_URL = os.environ.get("LLM_API_URL", "")
API_MODELE = os.environ.get("LLM_API_MODELE", "")
API_CLE = os.environ.get("LLM_API_CLE", "")

# Repli du fournisseur api : un second point de terminaison, au meme format
# OpenAI, sollicite seulement si le principal echoue apres ses propres
# tentatives (quota epuise, panne). Sans ces trois variables, le comportement
# est inchange : une panne du fournisseur principal fait echouer le run,
# exactement comme avant. La cle ne doit jamais figurer ailleurs qu'ici (elle
# vient d'un secret GitHub cote workflow, jamais du depot).
API_URL_REPLI = os.environ.get("LLM_API_URL_REPLI", "")
API_MODELE_REPLI = os.environ.get("LLM_API_MODELE_REPLI", "")
API_CLE_REPLI = os.environ.get("LLM_API_CLE_REPLI", "")
REPLI_ACTIF = bool(API_URL_REPLI and API_MODELE_REPLI and API_CLE_REPLI)

# Budget d'appels par execution. Les paliers gratuits comptent en requetes par
# jour et par modele : Gemini en accorde 20. Plutot que de laisser un lot
# volumineux epuiser le quota et echouer au milieu, on s'arrete avant. Les
# items non rediges ne sont pas marques vus et reviennent a l'execution
# suivante, exactement comme apres une panne.
BUDGET_APPELS = int(os.environ.get("LLM_BUDGET_APPELS", "0") or 0)
# Redaction des champs anglais servis par /en/frontier/. Mettre la variable a
# "0" les desactive sans toucher au code : le francais continue de sortir et la
# page anglaise retombe alors sur le texte francais.
RESUME_EN_ACTIF = os.environ.get("FRONTIERE_RESUME_EN", "1") not in ("0", "", "non", "false")
# Un item consomme au pire deux champs fois deux essais, quatre champs quand
# l'anglais est actif. Le budget doit refleter ce cout, sinon une execution
# s'arrete au milieu d'un item et publie du francais prive de son anglais.
APPELS_MAX_PAR_ITEM = 8 if RESUME_EN_ACTIF else 4
# Cout d'un item pour un rattrapage anglais seul : deux champs, deux essais.
# Le francais est deja ecrit et n'est pas retouche, donc reserver huit appels
# ferait s'arreter le lot avec de quoi rediger deux items de plus.
APPELS_MAX_ANGLAIS_SEUL = 4
_appels_effectues = 0
# Vrai une fois que le fournisseur principal a echoue et que la redaction est
# passee sur le repli. Persiste pour le reste de l'execution : retenter un
# fournisseur dont le quota est epuise ne ferait que perdre du temps sur
# chaque item suivant.
_bascule_repli = False


def appels_effectues():
    return _appels_effectues


def budget_epuise(appels_par_item=None):
    """Vrai s'il ne reste pas de quoi rediger un item entier.

    Le cout par item est par defaut celui d'une execution complete, francais
    et anglais. Un appelant qui ne redige qu'une partie des champs passe le
    sien : sinon le rattrapage anglais s'arreterait alors qu'il reste de quoi
    traiter des items.
    """
    if not BUDGET_APPELS:
        return False
    cout = APPELS_MAX_PAR_ITEM if appels_par_item is None else appels_par_item
    return _appels_effectues + cout > BUDGET_APPELS


class OllamaIndisponible(RuntimeError):
    """Le service de redaction ne repond pas. Panne, pas defaut de redaction."""


def modele_actif():
    """Nom du modele qui redige, quel que soit le fournisseur.

    Reflete la bascule : une fois le repli engage, les items suivants
    portent son nom, pas celui du fournisseur principal tombe en panne.
    """
    if FOURNISSEUR == "api":
        return API_MODELE_REPLI if _bascule_repli else API_MODELE
    return OLLAMA_MODEL

# Le prompt demande d'entrer directement dans le mecanisme. La liste couvre
# toute ouverture qui parle du papier au lieu de son contenu, pas seulement la
# formule "compte pour un economiste" : l'angle doit se lire seul, sous un
# titre qui annonce deja qu'il s'agit d'un papier.
FORMULES_ANGLE_INTERDITES = (
    "ce papier", "cet article", "cette étude", "cette etude",
    "ce travail", "cette recherche", "cette analyse",
    "dans ce papier", "dans cet article", "dans cette étude",
    "dans cette etude", "les auteurs",
)
# Le flux resume les travaux des autres. La premiere personne y fait passer
# l'auteur du site pour l'auteur du papier.
PREMIERE_PERSONNE = re.compile(
    r"\b(?:nous\s+(?:proposons|montrons|determinons|déterminons|presentons|présentons"
    r"|utilisons|developpons|développons|estimons|trouvons|appliquons|avons|constatons"
    r"|observons|analysons|etudions|étudions)"
    r"|notre\s+(?:methode|méthode|approche|analyse|modele|modèle|etude|étude|travail|papier|article)"
    r"|nos\s+(?:resultats|résultats|donnees|données|estimations|travaux))\b",
    re.IGNORECASE,
)
# Un demonstratif pluriel devant un nom abstrait renvoie a un passage que le
# lecteur n'a pas sous les yeux : l'angle et le resume sont lus seuls.
ANAPHORE_ORPHELINE = re.compile(
    r"\bces\s+(?:difficultés|difficultes|problèmes|problemes|limites|défis|defis"
    r"|enjeux|obstacles|contraintes|lacunes|questions|approches|méthodes|methodes)\b",
    re.IGNORECASE,
)
MOTS_OUTILS_ANGLAIS = {
    "the", "and", "of", "to", "with", "for", "from", "that", "this",
    "these", "those", "which", "were", "was", "are", "is", "it", "their",
    "between", "using", "into",
}
SYMBOLES_TEXTE_AUTORISES = {"%", "‰", "€", "$", "£", "°", "+", "=", "×"}

# Controles de langue. Mesures du 2026-08-02 sur les 3 modeles du banc
# (pipeline/benchmark) : l'elision manquante touche 5,8 % a 8,3 % des champs
# quel que soit le modele. Un modele plus gros ne la corrige pas, un validateur
# si. Le taux d'echec par champ etant faible, la reprise unique absorbe presque
# tous les cas et le volume du flux n'en souffre pas.
# Le y est exclu : "le yoga", "du yen" et "de yaourt" sont corrects, l'inclure
# produirait des faux positifs. Le h muet est exclu aussi, faute de pouvoir le
# distinguer du h aspire de "le heros" sans dictionnaire. Onze et ses derives
# sont exclus : "de onze modeles", "le onze novembre" sont corrects, onze ne
# s'elide pas (faux positif constate le 4 aout 2026 sur un resume valide).
_VOYELLES = "aàâeéèêëiîïoôuùûAÀÂEÉÈÊËIÎÏOÔUÙÛ"
ELISION_MANQUANTE = re.compile(
    rf"\b(?:le|la|du|de|ne|que|je|me|te|se)\s+(?!onz[ei])[{_VOYELLES}][\w'-]+",
    re.IGNORECASE,
)
DEMONSTRATIF_INCORRECT = re.compile(rf"\bce\s+[{_VOYELLES}][\w'-]+", re.IGNORECASE)
MOT_DOUBLE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)
# Faux ami : un trillion anglais vaut 10^12, le trillion francais 10^18. Repris
# tel quel, le chiffre est faux de six ordres de grandeur.
FAUX_AMI_NUMERIQUE = re.compile(r"\btrillions?\b", re.IGNORECASE)
FUITES_ANGLAISES = {
    "however", "moreover", "therefore", "furthermore", "whereas", "thereby",
    "incentive", "incentives", "findings", "insight", "insights",
    "trade-off", "tradeoff",
}

# Score multiplicatif (nb mots-cles eco x nb mots-cles ia) : exige la presence
# des deux dimensions a la fois, plutot qu'un score additif qui ferait remonter
# des papiers purement economiques sans aucun lien IA. Seuil recalibre a 3 le
# 2026-08-02 : 25 des 61 items audites, soit environ 5 par semaine, restent dans
# la selection principale. Les items sous le seuil rejoignent l'archive.
SEUIL_PUBLICATION = 3

MOTS_CLES_ECO = [
    "econom", "labor", "labour", "wage", "market", "policy", "welfare",
    "productiv", "causal", "econometric", "unemployment", "inequality",
    "fiscal", "monetary", "trade", "growth", "finance",
]
MOTS_CLES_IA = [
    "artificial intelligence", "machine learning", "deep learning", "llm",
    "large language model", "neural network", "algorithm", "automation",
    "gpt", "foundation model", "generative ai", "chatbot",
]

# Sources dont la nature economique est acquise avant toute lecture du texte :
# revues de l'AEA, working papers du NBER, colonnes VoxEU/CEPR, publications de
# la Banque du Canada. Un comite scientifique y a deja tranche la question que
# MOTS_CLES_ECO essaie de deviner.
#
# Motif du 2026-08-05 : "The Emerging Market for Intelligence: How Firms Buy
# and Sell AI" (JEP, DOI 10.1257/jep.20261506) a ete archive avec un score de 2.
# Son abstract parle de prix, de fournisseurs et de differenciation, mais aucun
# de ces mots ne figure dans MOTS_CLES_ECO, si bien qu'un article du Journal of
# Economic Perspectives a echoue au test « est-ce de l'economie ». Enrichir la
# liste de mots ou baisser le seuil corrigeait ce cas, mais faisait entrer par
# la meme porte des papiers d'ingenierie informatique sans contenu economique
# (mesure sur 127 items : +35 items pour un seuil a 2, +18 pour une liste
# enrichie, contre +5 ici, tous pertinents).
SOURCES_ECONOMIQUES = (
    "american economic review",
    "american economic journal",
    "journal of economic perspectives",
    "journal of economic literature",
    "aer",
    "nber",
    "voxeu",
    "cepr",
    "banque du canada",
    "bank of canada",
    "reserve federale",
    "federal reserve",
    "banque centrale europeenne",
    "european central bank",
    "bce",
    "ecb",
    "fonds monetaire international",
    "international monetary fund",
    "imf",
)
# Plancher applique au compte de mots economiques pour ces sources. Egal au
# seuil de publication : un seul mot-cle IA suffit alors a franchir la barre,
# ce qui revient a juger ces articles sur leur seule pertinence IA.
PLANCHER_ECO_SOURCE_ECONOMIQUE = SEUIL_PUBLICATION

THEMES_MOTS_CLES = {
    "inference-causale": ["causal", "identification", "instrument", "difference-in-differences", "rdd"],
    "llm": ["llm", "large language model", "gpt", "chatbot", "generative ai"],
    "prevision": ["forecast", "prevision", "prediction", "nowcast"],
    "travail-emploi": ["labor", "labour", "wage", "employment", "unemployment", "job"],
    "politique-publique": ["policy", "regulation", "government", "public"],
    "outils-recherche": ["tool", "software", "package", "library", "framework"],
    "donnees": ["dataset", "data", "survey", "administrative data"],
    "macro-finance": ["monetary", "fiscal", "gdp", "inflation", "finance", "growth"],
}


# Voir collect.py pour le raisonnement : les entrees des listes sont des
# racines tronquees comparees par sous-chaine, sauf ces acronymes, qui
# exigent un debut de mot. Sans cela « enrollment » compte comme « llm », et
# tout papier sur la scolarisation gagne un point d'intelligence artificielle.
MOTS_CLES_DEBUT_DE_MOT = {"llm"}
_MOTIFS_DEBUT_DE_MOT = {
    mot: re.compile(rf"\b{re.escape(mot)}", re.IGNORECASE)
    for mot in MOTS_CLES_DEBUT_DE_MOT
}


def mot_cle_present(texte_bas, mot):
    motif = _MOTIFS_DEBUT_DE_MOT.get(mot)
    if motif is not None:
        return bool(motif.search(texte_bas))
    return mot in texte_bas


def est_source_economique(source):
    """Vrai si la source publie de l'economie par construction.

    La comparaison se fait par sous-chaine sur le nom de source ecrit par
    collect.py, qui pour les revues AEA vaut le titre servi par Crossref
    (« Journal of Economic Perspectives ») et pour le NBER le libelle de la
    source configuree dans sources.yaml.
    """
    if not source:
        return False
    source_bas = source.lower()
    return any(marque in source_bas for marque in SOURCES_ECONOMIQUES)


def compter_mots_cles(texte, source=None):
    """Comptes economique et IA du texte, avant multiplication.

    Extrait de score_heuristique pour que les deux comptes soient conservables
    dans le flux : le score seul ne dit pas si un 6 vient de 2 x 3 ou de 3 x 2,
    et publish.py departage sur ce detail les articles a score egal.

    Pour une source deja economique (voir SOURCES_ECONOMIQUES), le compte
    economique est plancher : la revue ou le comite scientifique a deja
    etabli qu'il s'agit d'economie, et le vocabulaire d'un sous-champ
    (economie industrielle, organisation industrielle) n'a aucune raison de
    figurer dans une liste de mots generaliste. L'article est alors juge sur
    sa seule pertinence IA. Ailleurs, le calcul est inchange.
    """
    texte_bas = texte.lower()
    nb_eco = sum(1 for mot in MOTS_CLES_ECO if mot_cle_present(texte_bas, mot))
    nb_ia = sum(1 for mot in MOTS_CLES_IA if mot_cle_present(texte_bas, mot))
    if est_source_economique(source):
        nb_eco = max(nb_eco, PLANCHER_ECO_SOURCE_ECONOMIQUE)
    return nb_eco, nb_ia


def score_heuristique(texte, source=None):
    """Score de selection : nb de mots-cles economiques x nb de mots-cles IA."""
    nb_eco, nb_ia = compter_mots_cles(texte, source)
    return min(nb_eco * nb_ia, 10)


def themes_heuristique(texte):
    texte_bas = texte.lower()
    themes = [
        theme for theme, mots in THEMES_MOTS_CLES.items()
        if any(mot_cle_present(texte_bas, mot) for mot in mots)
    ]
    return themes[:3]


def _nombre_phrases(texte):
    return len(re.findall(r"[.!?]+(?=\s|$)", texte.strip()))


def _contient_caracteres_non_latins(texte):
    for caractere in texte:
        if caractere.isspace() or caractere.isdigit():
            continue
        if caractere.isalpha():
            if "LATIN" not in unicodedata.name(caractere, ""):
                return True
            continue
        if unicodedata.category(caractere).startswith("P"):
            continue
        if caractere in SYMBOLES_TEXTE_AUTORISES:
            continue
        return True
    return False


def _contient_anglais_residuel(texte):
    mots = re.findall(r"[a-z]+", texte.casefold())
    return sum(mot in MOTS_OUTILS_ANGLAIS for mot in mots) >= 3


def _anaphore_sans_antecedent(texte):
    """Vrai si un "ces X" renvoie a un X jamais introduit dans le texte.

    Le lecteur ne voit ni l'abstract ni les autres champs : un renvoi qui
    depasse les limites du texte affiche ne renvoie a rien.
    """
    for correspondance in ANAPHORE_ORPHELINE.finditer(texte):
        nom = correspondance.group(0).split()[-1].casefold()
        avant = texte[: correspondance.start()].casefold()
        racine = nom[:-1] if nom.endswith("s") else nom
        if racine not in avant:
            return True
    return False


def erreurs_redaction(texte):
    """Fautes de posture editoriale, communes au resume et a l'angle."""
    erreurs = []
    if PREMIERE_PERSONNE.search(texte):
        erreurs.append("premiere_personne")
    if _anaphore_sans_antecedent(texte):
        erreurs.append("anaphore_orpheline")
    return erreurs


def erreurs_langue(texte):
    """Retourne les fautes de francais detectables sans dictionnaire.

    Regles volontairement etroites : chacune est sans ambiguite, pour ne
    jamais rejeter une sortie correcte. Elles ne couvrent pas les accords en
    genre ni le style, qui restent du ressort d'une lecture humaine.
    """
    erreurs = []
    if ELISION_MANQUANTE.search(texte):
        erreurs.append("elision_manquante")
    if DEMONSTRATIF_INCORRECT.search(texte):
        erreurs.append("demonstratif_incorrect")
    if MOT_DOUBLE.search(texte):
        erreurs.append("mot_double")
    if FAUX_AMI_NUMERIQUE.search(texte):
        erreurs.append("faux_ami_numerique")
    if any(mot in FUITES_ANGLAISES for mot in re.findall(r"\b[a-z][a-z'-]+\b", texte)):
        erreurs.append("fuite_anglaise")
    return erreurs


def erreurs_resume(texte):
    """Retourne les controles echoues pour un resume produit par le LLM."""
    if not texte:
        return ["texte_vide"]
    erreurs = []
    if _nombre_phrases(texte) != 2:
        erreurs.append("nombre_phrases")
    if not texte.rstrip().endswith((".", "!", "?")):
        erreurs.append("ponctuation_finale")
    if _contient_caracteres_non_latins(texte):
        erreurs.append("caracteres_non_latins")
    if _contient_anglais_residuel(texte):
        erreurs.append("anglais_residuel")
    erreurs.extend(erreurs_langue(texte))
    erreurs.extend(erreurs_redaction(texte))
    return erreurs


def erreurs_angle(texte):
    """Retourne les controles echoues pour un angle economique produit par le LLM."""
    if not texte:
        return ["texte_vide"]
    erreurs = []
    if _nombre_phrases(texte) != 1:
        erreurs.append("nombre_phrases")
    if _contient_caracteres_non_latins(texte):
        erreurs.append("caracteres_non_latins")
    debut = texte.lstrip().casefold()
    if debut.startswith(FORMULES_ANGLE_INTERDITES):
        erreurs.append("formule_stereotypee")
    erreurs.extend(erreurs_langue(texte))
    erreurs.extend(erreurs_redaction(texte))
    return erreurs


# Symetrique de PREMIERE_PERSONNE cote anglais : le flux resume les travaux
# des autres, la premiere personne y ferait passer l'auteur du site pour
# l'auteur du papier.
PREMIERE_PERSONNE_EN = re.compile(r"\b(?:we|our|us)\b", re.IGNORECASE)

# Mots outils francais. Le seuil de trois evite de rejeter un titre cite ou un
# nom d'institution ("Banque de France") tout en attrapant une reponse rendue
# dans la mauvaise langue.
MOTS_OUTILS_FRANCAIS = {
    "les", "des", "une", "qui", "dans", "pour", "avec", "cette", "ces",
    "sont", "leur", "aux", "par", "sur", "est", "plus", "entre",
}


def _contient_francais_residuel(texte):
    mots = re.findall(r"[a-z\u00e0-\u00ff]+", texte.casefold())
    return sum(mot in MOTS_OUTILS_FRANCAIS for mot in mots) >= 3


def erreurs_redaction_en(texte):
    """Fautes de posture editoriale et de langue, cote anglais."""
    erreurs = []
    if PREMIERE_PERSONNE_EN.search(texte):
        erreurs.append("premiere_personne")
    if "\u2014" in texte:
        erreurs.append("tiret_cadratin")
    if _contient_francais_residuel(texte):
        erreurs.append("francais_residuel")
    if _contient_caracteres_non_latins(texte):
        erreurs.append("caracteres_non_latins")
    return erreurs


def erreurs_resume_en(texte):
    """Retourne les controles echoues pour un resume anglais produit par le LLM."""
    if not texte:
        return ["texte_vide"]
    erreurs = []
    if _nombre_phrases(texte) != 2:
        erreurs.append("nombre_phrases")
    if not texte.rstrip().endswith((".", "!", "?")):
        erreurs.append("ponctuation_finale")
    erreurs.extend(erreurs_redaction_en(texte))
    return erreurs


# Equivalent anglais de FORMULES_ANGLE_INTERDITES.
FORMULES_ANGLE_EN_INTERDITES = (
    "this paper", "this article", "this study", "this work",
    "this research", "this analysis", "the authors", "in this paper",
    "in this article", "in this study",
)


def erreurs_angle_en(texte):
    """Retourne les controles echoues pour un angle economique anglais."""
    if not texte:
        return ["texte_vide"]
    erreurs = []
    if _nombre_phrases(texte) != 1:
        erreurs.append("nombre_phrases")
    if texte.lstrip().casefold().startswith(FORMULES_ANGLE_EN_INTERDITES):
        erreurs.append("formule_stereotypee")
    erreurs.extend(erreurs_redaction_en(texte))
    return erreurs


def _nombres(texte):
    """Valeurs numeriques d'un texte, francais ou anglais.

    Deux normalisations, sans lesquelles le meme nombre compte pour deux :
    le separateur de milliers francais (380 000) est retire, et la virgule
    decimale (2,32) devient un point.
    """
    sans_milliers = re.sub(r"(?<=\d)[   ](?=\d{3}(?!\d))", "", texte)
    normalise = re.sub(r"(?<=\d),(?=\d)", ".", sans_milliers)
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", normalise)}


def erreurs_invention(texte, source):
    """Chiffres presents dans le texte genere mais absents de la source.

    Ne verifie pas le sens, seulement la presence : une lecture humaine
    resterait necessaire pour juger si un chiffre repris est bien employe.
    Ce filtre intercepte seulement le cas le plus grave sans elle, un
    chiffre materiellement absent du titre et du resume d'origine.

    Le facteur mille est tolere parce que le prompt exige lui-meme une
    conversion : trillion devient mille milliards, donc 380 dans la source
    devient legitimement 380 000 dans le texte. Sans cette tolerance, le
    filtre rejetterait la traduction qu'il demande.
    """
    if not texte or not source:
        return []
    nombres_source = _nombres(source)
    autorises = nombres_source | {valeur * 1000 for valeur in nombres_source}
    inventes = _nombres(texte) - autorises
    return ["chiffre_invente"] if inventes else []


def _generer_avec_reprise(generateur, validateur):
    """Tente deux generations au maximum et retourne la premiere sortie valide."""
    for _ in range(2):
        texte = generateur()
        if texte and validateur(texte):
            return texte
    return None


def _requete_ollama(requests, prompt):
    reponse = requests.post(
        OLLAMA_URL,
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=OLLAMA_TIMEOUT,
    )
    reponse.raise_for_status()
    return reponse.json().get("response", "").strip() or None


def _requete_api(requests, prompt, url, modele, cle):
    """Appelle un service au format OpenAI : DeepSeek, Gemini, Claude (endpoint
    compatible) et equivalents. url/modele/cle varient selon qu'il s'agit du
    fournisseur principal ou de son repli.
    """
    reponse = requests.post(
        url,
        headers={"Authorization": f"Bearer {cle}"},
        json={
            "model": modele,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
        timeout=OLLAMA_TIMEOUT,
    )
    reponse.raise_for_status()
    choix = reponse.json().get("choices") or []
    if not choix:
        return None
    return (choix[0].get("message", {}).get("content") or "").strip() or None


def _delai_avant_reprise(erreur, tentative):
    """Attente avant nouvel essai, allongee si le service limite le debit.

    Un 429 n'est ni une panne ni un defaut de redaction : le service demande
    d'attendre. Les paliers gratuits en imposent un a quelques appels par
    minute, ce qui suffirait sinon a interrompre un lot en cours de route.
    Un 503 est la meme situation vue d'en face : le modele est sature, pas
    ferme. Lui laisser deux secondes revient a abandonner tout de suite.
    """
    reponse = getattr(erreur, "response", None)
    code = getattr(reponse, "status_code", None) if reponse is not None else None
    if code == 429:
        entete = (reponse.headers or {}).get("Retry-After")
        if entete and str(entete).strip().isdigit():
            return min(int(entete), PAUSE_MAX_DEBIT)
        return min(PAUSE_AVANT_REPRISE * 2 ** (tentative + 3), PAUSE_MAX_DEBIT)
    if code in CODES_SATURATION:
        return min(PAUSE_AVANT_REPRISE * 2 ** (tentative + 2), PAUSE_MAX_DEBIT)
    return PAUSE_AVANT_REPRISE


def _tenter(requests, prompt, requete, tentatives):
    """Boucle de tentatives generique, commune au fournisseur principal et a
    son repli, pour ne pas dupliquer la logique de pause entre les deux.
    """
    global _appels_effectues
    derniere_erreur = None
    for tentative in range(tentatives):
        try:
            _appels_effectues += 1
            return requete(requests, prompt)
        except Exception as erreur:
            derniere_erreur = erreur
            if tentative < tentatives - 1:
                time.sleep(_delai_avant_reprise(erreur, tentative))
    raise OllamaIndisponible(derniere_erreur)


def _appel_ollama(prompt):
    """Retourne le texte genere par le fournisseur configure.

    Pour le fournisseur api, bascule sur le repli (LLM_API_URL_REPLI et
    consorts) si le principal echoue apres ses propres tentatives. La
    bascule vaut pour le reste de l'execution : une fois engagee, les items
    suivants vont directement au repli, sans retenter un fournisseur dont le
    quota est epuise. Le budget d'appels (LLM_BUDGET_APPELS) reste un seul
    compteur global, quel que soit le point de terminaison sollicite.

    Leve OllamaIndisponible si le service (et son repli, le cas echeant) ne
    repond toujours pas apres les tentatives prevues. Une panne de transport
    n'est pas un echec de redaction : elle ne doit pas faire marquer l'item
    comme vu, sinon il ne serait jamais repeche.
    """
    import requests

    global _bascule_repli

    if FOURNISSEUR != "api":
        return _tenter(requests, prompt, _requete_ollama, tentatives=2)

    if _bascule_repli:
        return _tenter(
            requests, prompt,
            lambda req, p: _requete_api(req, p, API_URL_REPLI, API_MODELE_REPLI, API_CLE_REPLI),
            tentatives=TENTATIVES_API,
        )

    try:
        return _tenter(
            requests, prompt,
            lambda req, p: _requete_api(req, p, API_URL, API_MODELE, API_CLE),
            tentatives=TENTATIVES_API,
        )
    except OllamaIndisponible as erreur_principale:
        if not REPLI_ACTIF:
            raise
        print(
            f"Fournisseur principal indisponible ({API_MODELE}) : "
            f"{erreur_principale}. Bascule sur le repli ({API_MODELE_REPLI}) "
            "pour le reste de l'execution.",
            file=sys.stderr,
        )
        _bascule_repli = True
        return _tenter(
            requests, prompt,
            lambda req, p: _requete_api(req, p, API_URL_REPLI, API_MODELE_REPLI, API_CLE_REPLI),
            tentatives=TENTATIVES_API,
        )


def resume_ollama(titre, abstract):
    """Resume en 2 phrases francaises, ou None si Ollama echoue (fallback heuristique)."""
    if not abstract:
        return None
    return _appel_ollama(construire_prompt_resume(titre, abstract))


def construire_prompt_resume(titre, abstract):
    return (
        "Tu resumes un papier de recherche en francais, pour un economiste presse. "
        "Tu n'es pas l'auteur du papier : ecris a la troisieme personne, jamais "
        "nous, notre ni nos. Le lecteur ne voit que tes deux phrases, donc "
        "n'ecris pas ces difficultes ni ces problemes sans les avoir nommes avant. "
        "Ecris exactement 2 phrases en francais, factuelles, sans inventer de chiffre "
        "ou de resultat absent du texte source. N'ajoute aucun prefixe ni commentaire, "
        "seulement les 2 phrases. N'utilise pas de tiret cadratin. Respecte les "
        "elisions : ecris d'un, l'unite, qu'Amazon, et non de un, la unite, que Amazon. "
        "Si le texte source dit trillion, ecris mille milliards.\n\n"
        f"Titre : {titre}\n"
        f"Resume original (anglais) : {abstract[:1500]}\n\n"
        "Resume en francais (2 phrases) :"
    )


def angle_eco_ollama(titre, abstract):
    """Une phrase 'pourquoi ca compte pour un economiste', ou None si Ollama echoue."""
    return _appel_ollama(construire_prompt_angle(titre, abstract))


def construire_prompt_angle(titre, abstract):
    return (
        "Rédige une seule phrase en français sur le mécanisme ou l'enjeu du papier "
        "pour l'analyse économique. Commence directement par ce mécanisme ou cet enjeu. "
        "Ne commence pas par « Ce papier », « Cet article » ou « Cette étude », ni par "
        "une formule annonçant son intérêt pour un économiste. Ne répète pas le titre "
        "mot pour mot et n'invente aucun chiffre ou résultat absent du texte source. "
        "N'ajoute aucun préfixe ni commentaire et n'utilise pas de tiret cadratin. "
        "Tu n'es pas l'auteur du papier : n'écris jamais nous, notre ni nos. "
        "La phrase est lue seule, sans le résumé : n'écris pas « ces difficultés » "
        "ni « ces problèmes » sans les avoir nommés dans la phrase même. "
        "Respecte les élisions : écris d'un, l'unité, qu'Amazon, et non de un, "
        "la unité, que Amazon. Si le texte source dit trillion, écris mille milliards.\n\n"
        f"Titre : {titre}\n"
        f"Resume original (anglais) : {abstract[:1500]}\n\n"
        "Phrase :"
    )


def resume_en_ollama(titre, abstract):
    """Resume anglais en 2 phrases, ou None si le service echoue.

    Redige depuis l'abstract d'origine, qui est deja en anglais, jamais par
    traduction du resume francais : traduire une traduction accumule les
    ecarts alors que le texte source est disponible ici.
    """
    if not abstract:
        return None
    return _appel_ollama(construire_prompt_resume_en(titre, abstract))


def construire_prompt_resume_en(titre, abstract):
    return (
        "You are summarizing a research paper in English for a busy economist. "
        "You are not the author: write in the third person, never we, our or us. "
        "The reader sees only your two sentences, so do not write these "
        "difficulties or these problems without naming them first. "
        "Write exactly 2 factual sentences in English. Do not invent any figure "
        "or result absent from the source text. Add no prefix and no comment, "
        "only the 2 sentences. Do not use an em dash.\n\n"
        f"Title: {titre}\n"
        f"Original abstract: {abstract[:1500]}\n\n"
        "Summary in English (2 sentences):"
    )


def angle_eco_en_ollama(titre, abstract):
    """Une phrase anglaise sur l'enjeu pour l'analyse economique, ou None."""
    return _appel_ollama(construire_prompt_angle_en(titre, abstract))


def construire_prompt_angle_en(titre, abstract):
    return (
        "Write a single English sentence on the mechanism or the issue the paper "
        "raises for economic analysis. Start directly with that mechanism or "
        "issue. Do not start with This paper, This article, This study or any "
        "phrase announcing its interest to an economist. Do not repeat the title "
        "word for word and do not invent any figure or result absent from the "
        "source text. Add no prefix and no comment, and do not use an em dash. "
        "You are not the author: never write we, our or us. The sentence is read "
        "on its own, without the summary: do not write these difficulties or "
        "these problems without naming them in the sentence itself.\n\n"
        f"Title: {titre}\n"
        f"Original abstract: {abstract[:1500]}\n\n"
        "Sentence:"
    )


def enregistrer_execution(nb_eligibles, nb_publies, nb_reportes, nb_non_publies_validation):
    """Ajoute cette execution a l'historique lu par verifier_sante.py.

    Le fichier est committe : c'est la seule facon pour une execution
    planifiee de savoir ce qu'a produit la precedente.
    """
    historique = []
    if SANTE.exists():
        try:
            historique = json.loads(SANTE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            historique = []
    historique.append({
        "date": date.today().isoformat(),
        "fournisseur": FOURNISSEUR or "aucun",
        "bascule_repli": _bascule_repli,
        "nb_eligibles": nb_eligibles,
        "nb_publies": nb_publies,
        "nb_reportes": nb_reportes,
        "nb_rejetes_validation": nb_non_publies_validation,
    })
    historique = historique[-NB_EXECUTIONS_CONSERVEES:]
    SANTE.parent.mkdir(parents=True, exist_ok=True)
    SANTE.write_text(json.dumps(historique, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    candidats = json.loads(ENTREE.read_text(encoding="utf-8")) if ENTREE.exists() else []
    deja_vus = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}

    cures = []
    candidats_archives = []
    nouveaux_vus = dict(deja_vus)
    nb_deja_vus = 0
    nb_eligibles = 0
    nb_non_publies_validation = 0
    nb_reportes = 0

    for candidat in candidats:
        if candidat["id"] in deja_vus:
            nb_deja_vus += 1
            continue

        texte_complet = f"{candidat['titre']} {candidat.get('abstract', '')}"
        # Les deux comptes sont conserves dans l'entree : l'abstract, seul
        # texte anglais sur lequel le score se calcule, n'est pas verse dans
        # le flux, donc publish.py ne pourrait pas les recalculer plus tard.
        nb_eco, nb_ia = compter_mots_cles(texte_complet, candidat.get("source"))
        score = score_heuristique(texte_complet, candidat.get("source"))

        if score < SEUIL_PUBLICATION:
            nouveaux_vus[candidat["id"]] = {"score": score, "traite": True}
            candidats_archives.append({
                "id": candidat["id"],
                "titre": candidat["titre"],
                "url": candidat["url"],
                "source": candidat["source"],
                "type": candidat["type"],
                "date_publication": candidat.get("date_publication"),
                "themes": themes_heuristique(texte_complet),
                "score": score,
                "nb_eco": nb_eco,
                "nb_ia": nb_ia,
                "auteurs": candidat.get("auteurs", ""),
                "signal": False,
            })
            continue
        nb_eligibles += 1

        if not LLM_ACTIF or budget_epuise():
            # Sans service de redaction, ou sans budget d'appels restant,
            # l'item n'est ni publiable ni juge : il reste non vu pour etre
            # repris a l'execution suivante.
            nb_reportes += 1
            continue

        resume_fr = _generer_avec_reprise(
            lambda: resume_ollama(
                candidat["titre"], candidat.get("abstract", "")
            ),
            lambda texte: not erreurs_resume(texte)
            and not erreurs_invention(texte, texte_complet),
        )
        if not resume_fr:
            nouveaux_vus[candidat["id"]] = {"score": score, "traite": True}
            nb_non_publies_validation += 1
            continue

        angle_eco = _generer_avec_reprise(
            lambda: angle_eco_ollama(
                candidat["titre"], candidat.get("abstract", "")
            ),
            lambda texte: not erreurs_angle(texte)
            and not erreurs_invention(texte, texte_complet),
        )
        if not angle_eco:
            nouveaux_vus[candidat["id"]] = {"score": score, "traite": True}
            nb_non_publies_validation += 1
            continue

        # Champs anglais : jamais bloquants. Un echec de generation ou de
        # validation laisse le champ absent et la page anglaise sert le texte
        # francais (frontiere/frontiere.js, resumeDe). Publier un item complet
        # en francais vaut mieux que le retenir pour un defaut cote anglais.
        resume_en = None
        angle_eco_en = None
        if RESUME_EN_ACTIF:
            # La panne du service est rattrapee ici, et seulement ici. Plus
            # haut, elle doit remonter : un item sans francais n'est pas
            # publiable. A ce point le francais est ecrit et valide, donc une
            # panne survenue entre-temps ne doit pas le faire perdre.
            try:
                resume_en = _generer_avec_reprise(
                    lambda: resume_en_ollama(
                        candidat["titre"], candidat.get("abstract", "")
                    ),
                    lambda texte: not erreurs_resume_en(texte)
                    and not erreurs_invention(texte, texte_complet),
                )
                angle_eco_en = _generer_avec_reprise(
                    lambda: angle_eco_en_ollama(
                        candidat["titre"], candidat.get("abstract", "")
                    ),
                    lambda texte: not erreurs_angle_en(texte)
                    and not erreurs_invention(texte, texte_complet),
                )
            except OllamaIndisponible:
                resume_en = None
                angle_eco_en = None

        nouveaux_vus[candidat["id"]] = {"score": score, "traite": True}
        entree = {
            "id": candidat["id"],
            "titre": candidat["titre"],
            "url": candidat["url"],
            "source": candidat["source"],
            "type": candidat["type"],
            "date_publication": candidat.get("date_publication"),
            "resume_fr": resume_fr,
            "angle_eco": angle_eco,
            "themes": themes_heuristique(texte_complet),
            "score": score,
            "nb_eco": nb_eco,
            "nb_ia": nb_ia,
            "auteurs": candidat.get("auteurs", ""),
            "signal": False,
        }
        entree["llm"] = modele_actif()
        # Champs absents plutot que vides : frontiere.js teste leur presence.
        if resume_en:
            entree["resume_en"] = resume_en
        if angle_eco_en:
            entree["angle_eco_en"] = angle_eco_en

        cures.append(entree)

    SORTIE.write_text(json.dumps(cures, ensure_ascii=False, indent=2), encoding="utf-8")
    SORTIE_ARCHIVE.write_text(
        json.dumps(candidats_archives, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    SEEN.write_text(json.dumps(nouveaux_vus, ensure_ascii=False, indent=2), encoding="utf-8")
    enregistrer_execution(nb_eligibles, len(cures), nb_reportes, nb_non_publies_validation)

    nb_llm = sum(1 for c in cures if c.get("llm"))
    print(f"Candidats traites : {len(candidats)}")
    print(f"Deja vus (ignores) : {nb_deja_vus}")
    print(f"Eligibles (score >= {SEUIL_PUBLICATION}) : {nb_eligibles}")
    print(f"Publies apres validation : {len(cures)}")
    print(f"Transmis a l'archive (score < {SEUIL_PUBLICATION}) : {len(candidats_archives)}")
    print(f"Redaction : {FOURNISSEUR} ({modele_actif()})" if LLM_ACTIF else "Redaction : aucune (heuristique seul)")
    if LLM_ACTIF and _bascule_repli:
        print(
            f"Bascule sur le repli engagee : {API_MODELE} indisponible, "
            f"{API_MODELE_REPLI} a pris le relais pour le reste de l'execution."
        )
    if LLM_ACTIF:
        print(f"Resumes rediges et valides : {nb_llm}/{len(cures)}")
        if RESUME_EN_ACTIF:
            nb_en = sum(1 for c in cures if c.get("resume_en"))
            print(f"Resumes anglais rediges et valides : {nb_en}/{len(cures)}")
        budget = f" sur un budget de {BUDGET_APPELS}" if BUDGET_APPELS else ""
        print(f"Appels au modele : {appels_effectues()}{budget}")
    print(
        "Items non publies apres deux echecs de validation : "
        f"{nb_non_publies_validation}"
    )
    print(f"Items reportes au prochain run (non marques vus) : {nb_reportes}")
    print(f"Ecrits dans {SORTIE}")
    print(f"Ecrits dans {SORTIE_ARCHIVE}")


if __name__ == "__main__":
    try:
        main()
    except OllamaIndisponible as erreur:
        # Arret atomique : main() n'ecrit qu'a la toute fin, donc ni seen.json
        # ni les fichiers de sortie ne sont touches. Le prochain run reprend
        # les memes candidats. Le code de sortie 1 fait echouer le workflow,
        # ce qui rend la panne visible au lieu de la laisser passer en silence.
        print(
            "Service de redaction indisponible : "
            f"{OLLAMA_URL} ({erreur}). Aucun fichier ecrit, aucun item marque "
            "vu. Le run est interrompu, les candidats seront repris tels quels.",
            file=sys.stderr,
        )
        sys.exit(1)
