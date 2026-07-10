"""Curation pour La Frontiere.

Lit pipeline/_candidats_bruts.json et pipeline/seen.json, calcule un score
heuristique et un resume extrait pour chaque candidat non deja vu, et ecrit
pipeline/_candidats_cures.json (uniquement les candidats au-dessus du seuil).

Le score reste TOUJOURS heuristique (deterministe, auditable) : un LLM ne
sert jamais au tri, seulement a la redaction (resume + angle economiste),
et seulement sur les items deja retenus par le seuil.

Mode par defaut : aucune dependance externe (resume_heuristique = extrait de
l'abstract original). Mode optionnel Ollama (variable d'environnement
FRONTIERE_LLM=ollama) : resume_ollama()/angle_eco_ollama() appellent un
modele Ollama local (installe dans le runner GitHub Actions) pour rediger un
resume en francais et une ligne "pourquoi ca compte pour un economiste".
Toute erreur (Ollama absent, timeout, reponse vide) retombe silencieusement
sur le mode heuristique pour cet item : le run ne casse jamais.
"""

import io
import json
import os
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ICI = Path(__file__).parent
ENTREE = ICI / "_candidats_bruts.json"
SORTIE = ICI / "_candidats_cures.json"
SEEN = ICI / "seen.json"

LLM_ACTIF = os.environ.get("FRONTIERE_LLM") == "ollama"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = 60

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


def resume_heuristique(abstract):
    if not abstract:
        return ""
    extrait = abstract[:280]
    derniere_phrase = max(extrait.rfind(". "), extrait.rfind(".\n"))
    if derniere_phrase > 40:
        extrait = extrait[: derniere_phrase + 1]
    return f"[Extrait original, traduction non disponible] {extrait.strip()}"


def themes_heuristique(texte):
    texte_bas = texte.lower()
    themes = [
        theme for theme, mots in THEMES_MOTS_CLES.items()
        if any(mot in texte_bas for mot in mots)
    ]
    return themes[:3]


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
        "En une seule phrase en francais, explique pourquoi ce papier compte pour un "
        "economiste. Ne repete pas le titre mot pour mot, n'invente aucun chiffre absent "
        "du texte source. Reponds seulement avec la phrase.\n\n"
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

    for candidat in candidats:
        if candidat["id"] in deja_vus:
            nb_deja_vus += 1
            continue

        texte_complet = f"{candidat['titre']} {candidat.get('abstract', '')}"
        score = score_heuristique(texte_complet)
        nouveaux_vus[candidat["id"]] = {"score": score, "traite": True}

        if score < SEUIL_PUBLICATION:
            continue

        resume_fr = resume_heuristique(candidat.get("abstract", ""))
        angle_eco = ""
        llm_utilise = None

        if LLM_ACTIF:
            resume_llm = resume_ollama(candidat["titre"], candidat.get("abstract", ""))
            if resume_llm:
                resume_fr = resume_llm
                llm_utilise = OLLAMA_MODEL
                angle_llm = angle_eco_ollama(candidat["titre"], candidat.get("abstract", ""))
                if angle_llm:
                    angle_eco = angle_llm

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
        if llm_utilise:
            entree["llm"] = llm_utilise

        cures.append(entree)

    SORTIE.write_text(json.dumps(cures, ensure_ascii=False, indent=2), encoding="utf-8")
    SEEN.write_text(json.dumps(nouveaux_vus, ensure_ascii=False, indent=2), encoding="utf-8")

    nb_llm = sum(1 for c in cures if c.get("llm"))
    print(f"Candidats traites : {len(candidats)}")
    print(f"Deja vus (ignores) : {nb_deja_vus}")
    print(f"Retenus (score >= {SEUIL_PUBLICATION}) : {len(cures)}")
    print(f"Mode LLM actif : {LLM_ACTIF} ({OLLAMA_MODEL})" if LLM_ACTIF else "Mode LLM actif : non (heuristique seul)")
    if LLM_ACTIF:
        print(f"Resumes rediges par Ollama : {nb_llm}/{len(cures)} (le reste retombe sur l'extrait heuristique)")
    print(f"Ecrits dans {SORTIE}")


if __name__ == "__main__":
    main()
