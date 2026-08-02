"""Curation pour La Frontiere.

Lit pipeline/_candidats_bruts.json et pipeline/seen.json, calcule un score
heuristique et un resume extrait pour chaque candidat non deja vu, et ecrit
pipeline/_candidats_cures.json (uniquement les candidats au-dessus du seuil).

Le score reste TOUJOURS heuristique (deterministe, auditable) : un LLM ne
sert jamais au tri, seulement a la redaction (resume + angle economiste),
et seulement sur les items deja retenus par le seuil.

En mode Ollama (variable d'environnement FRONTIERE_LLM=ollama),
resume_ollama()/angle_eco_ollama() appellent un modele local pour rediger un
resume en francais et une ligne d'analyse economique. Chaque sortie est
validee separement. Une sortie invalide est relancee une fois, puis l'item
n'est pas publie si le second essai echoue. Aucun extrait anglais n'est publie
en repli.
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ICI = Path(__file__).parent
ENTREE = ICI / "_candidats_bruts.json"
SORTIE = ICI / "_candidats_cures.json"
SEEN = ICI / "seen.json"

LLM_ACTIF = os.environ.get("FRONTIERE_LLM") == "ollama"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = 60

FORMULES_ANGLE_INTERDITES = (
    "ce papier compte pour un",
    "cet article compte pour un",
    "cette étude compte pour un",
    "cette etude compte pour un",
    "ce travail compte pour un",
)
MOTS_OUTILS_ANGLAIS = {
    "the", "and", "of", "to", "with", "for", "from", "that", "this",
    "these", "those", "which", "were", "was", "are", "is", "it", "their",
    "between", "using", "into",
}
SYMBOLES_TEXTE_AUTORISES = {"%", "‰", "€", "$", "£", "°", "+", "=", "×"}

# Score multiplicatif (nb mots-cles eco x nb mots-cles ia) : exige la presence
# des deux dimensions a la fois, plutot qu'un score additif qui ferait remonter
# des papiers purement economiques sans aucun lien IA. Seuil calibre a 2 (pas 4)
# apres test sur donnees reelles le 2026-07-10 : avec des grilles de mots-cles
# simples (pas de LLM), un seuil de 4 ne laissait passer qu'1 item sur 62 candidats.
# A recalibrer si le volume reel du flux se revele trop bruyant ou trop maigre.
SEUIL_PUBLICATION = 2

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


def score_heuristique(texte):
    texte_bas = texte.lower()
    nb_eco = sum(1 for mot in MOTS_CLES_ECO if mot in texte_bas)
    nb_ia = sum(1 for mot in MOTS_CLES_IA if mot in texte_bas)
    return min(nb_eco * nb_ia, 10)


def themes_heuristique(texte):
    texte_bas = texte.lower()
    themes = [
        theme for theme, mots in THEMES_MOTS_CLES.items()
        if any(mot in texte_bas for mot in mots)
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
    return erreurs


def _generer_avec_reprise(generateur, validateur):
    """Tente deux generations au maximum et retourne la premiere sortie valide."""
    for _ in range(2):
        texte = generateur()
        if texte and validateur(texte):
            return texte
    return None


def _appel_ollama(prompt):
    """Retourne le texte genere par Ollama, ou None si indisponible/invalide."""
    import requests

    try:
        reponse = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        reponse.raise_for_status()
        texte = reponse.json().get("response", "").strip()
        return texte or None
    except Exception:
        return None


def resume_ollama(titre, abstract):
    """Resume en 2 phrases francaises, ou None si Ollama echoue (fallback heuristique)."""
    if not abstract:
        return None
    prompt = (
        "Tu resumes un papier de recherche en francais, pour un economiste presse. "
        "Ecris exactement 2 phrases en francais, factuelles, sans inventer de chiffre "
        "ou de resultat absent du texte source. N'ajoute aucun prefixe ni commentaire, "
        "seulement les 2 phrases.\n\n"
        f"Titre : {titre}\n"
        f"Resume original (anglais) : {abstract[:1500]}\n\n"
        "Resume en francais (2 phrases) :"
    )
    return _appel_ollama(prompt)


def angle_eco_ollama(titre, abstract):
    """Une phrase 'pourquoi ca compte pour un economiste', ou None si Ollama echoue."""
    prompt = (
        "Rédige une seule phrase en français sur le mécanisme ou l'enjeu du papier "
        "pour l'analyse économique. Commence directement par ce mécanisme ou cet enjeu. "
        "Ne commence pas par « Ce papier », « Cet article » ou « Cette étude », ni par "
        "une formule annonçant son intérêt pour un économiste. Ne répète pas le titre "
        "mot pour mot et n'invente aucun chiffre ou résultat absent du texte source. "
        "N'ajoute aucun préfixe ni commentaire.\n\n"
        f"Titre : {titre}\n"
        f"Resume original (anglais) : {abstract[:1500]}\n\n"
        "Phrase :"
    )
    return _appel_ollama(prompt)


def main():
    candidats = json.loads(ENTREE.read_text(encoding="utf-8")) if ENTREE.exists() else []
    deja_vus = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}

    cures = []
    nouveaux_vus = dict(deja_vus)
    nb_deja_vus = 0
    nb_eligibles = 0
    nb_non_publies_validation = 0

    for candidat in candidats:
        if candidat["id"] in deja_vus:
            nb_deja_vus += 1
            continue

        texte_complet = f"{candidat['titre']} {candidat.get('abstract', '')}"
        score = score_heuristique(texte_complet)
        nouveaux_vus[candidat["id"]] = {"score": score, "traite": True}

        if score < SEUIL_PUBLICATION:
            continue
        nb_eligibles += 1

        if not LLM_ACTIF:
            nb_non_publies_validation += 1
            continue

        resume_fr = _generer_avec_reprise(
            lambda: resume_ollama(
                candidat["titre"], candidat.get("abstract", "")
            ),
            lambda texte: not erreurs_resume(texte),
        )
        if not resume_fr:
            nb_non_publies_validation += 1
            continue

        angle_eco = _generer_avec_reprise(
            lambda: angle_eco_ollama(
                candidat["titre"], candidat.get("abstract", "")
            ),
            lambda texte: not erreurs_angle(texte),
        )
        if not angle_eco:
            nb_non_publies_validation += 1
            continue

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
            "auteurs": candidat.get("auteurs", ""),
            "signal": False,
        }
        entree["llm"] = OLLAMA_MODEL

        cures.append(entree)

    SORTIE.write_text(json.dumps(cures, ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN.write_text(json.dumps(nouveaux_vus, ensure_ascii=False, indent=2), encoding="utf-8")

    nb_llm = sum(1 for c in cures if c.get("llm"))
    print(f"Candidats traites : {len(candidats)}")
    print(f"Deja vus (ignores) : {nb_deja_vus}")
    print(f"Eligibles (score >= {SEUIL_PUBLICATION}) : {nb_eligibles}")
    print(f"Publies apres validation : {len(cures)}")
    print(f"Mode LLM actif : {LLM_ACTIF} ({OLLAMA_MODEL})" if LLM_ACTIF else "Mode LLM actif : non (heuristique seul)")
    if LLM_ACTIF:
        print(f"Resumes rediges et valides par Ollama : {nb_llm}/{len(cures)}")
    print(
        "Items non publies apres echec ou absence de validation LLM : "
        f"{nb_non_publies_validation}"
    )
    print(f"Ecrits dans {SORTIE}")


if __name__ == "__main__":
    main()
