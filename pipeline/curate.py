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

Deux echecs sont distingues, parce qu'ils n'appellent pas la meme reaction :
  - echec de validation : le modele a repondu, mal. L'item est marque vu et
    ne sera pas repeche. C'est la politique arretee.
  - service indisponible : le modele n'a pas repondu. Rien n'est ecrit, aucun
    item n'est marque vu, le script sort en erreur. Une panne ne doit jamais
    consommer definitivement des articles.
"""

import json
import os
import re
import sys
import time
import unicodedata
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

API_URL = os.environ.get("LLM_API_URL", "")
API_MODELE = os.environ.get("LLM_API_MODELE", "")
API_CLE = os.environ.get("LLM_API_CLE", "")


class OllamaIndisponible(RuntimeError):
    """Le service de redaction ne repond pas. Panne, pas defaut de redaction."""


def modele_actif():
    """Nom du modele qui redige, quel que soit le fournisseur."""
    return API_MODELE if FOURNISSEUR == "api" else OLLAMA_MODEL

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
# distinguer du h aspire de "le heros" sans dictionnaire.
_VOYELLES = "aàâeéèêëiîïoôuùûAÀÂEÉÈÊËIÎÏOÔUÙÛ"
ELISION_MANQUANTE = re.compile(
    rf"\b(?:le|la|du|de|ne|que|je|me|te|se)\s+[{_VOYELLES}][\w'-]+", re.IGNORECASE
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


def _requete_api(requests, prompt):
    """Appelle un service au format OpenAI : DeepSeek, Gemini et equivalents."""
    reponse = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {API_CLE}"},
        json={
            "model": API_MODELE,
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


def _appel_ollama(prompt):
    """Retourne le texte genere par le fournisseur configure.

    Leve OllamaIndisponible si le service ne repond pas apres deux tentatives.
    Une panne de transport n'est pas un echec de redaction : elle ne doit pas
    faire marquer l'item comme vu, sinon il ne serait jamais repeche.
    """
    import requests

    requete = _requete_api if FOURNISSEUR == "api" else _requete_ollama
    derniere_erreur = None
    for tentative in range(2):
        try:
            return requete(requests, prompt)
        except Exception as erreur:
            derniere_erreur = erreur
            if tentative == 0:
                time.sleep(PAUSE_AVANT_REPRISE)
    raise OllamaIndisponible(derniere_erreur)


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
        score = score_heuristique(texte_complet)

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
                "auteurs": candidat.get("auteurs", ""),
                "signal": False,
            })
            continue
        nb_eligibles += 1

        if not LLM_ACTIF:
            # Sans service de redaction, l'item n'est ni publiable ni juge :
            # il reste non vu pour etre repris quand le LLM sera disponible.
            nb_reportes += 1
            continue

        resume_fr = _generer_avec_reprise(
            lambda: resume_ollama(
                candidat["titre"], candidat.get("abstract", "")
            ),
            lambda texte: not erreurs_resume(texte),
        )
        if not resume_fr:
            nouveaux_vus[candidat["id"]] = {"score": score, "traite": True}
            nb_non_publies_validation += 1
            continue

        angle_eco = _generer_avec_reprise(
            lambda: angle_eco_ollama(
                candidat["titre"], candidat.get("abstract", "")
            ),
            lambda texte: not erreurs_angle(texte),
        )
        if not angle_eco:
            nouveaux_vus[candidat["id"]] = {"score": score, "traite": True}
            nb_non_publies_validation += 1
            continue

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
            "auteurs": candidat.get("auteurs", ""),
            "signal": False,
        }
        entree["llm"] = modele_actif()

        cures.append(entree)

    SORTIE.write_text(json.dumps(cures, ensure_ascii=False, indent=2), encoding="utf-8")
    SORTIE_ARCHIVE.write_text(
        json.dumps(candidats_archives, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    SEEN.write_text(json.dumps(nouveaux_vus, ensure_ascii=False, indent=2), encoding="utf-8")

    nb_llm = sum(1 for c in cures if c.get("llm"))
    print(f"Candidats traites : {len(candidats)}")
    print(f"Deja vus (ignores) : {nb_deja_vus}")
    print(f"Eligibles (score >= {SEUIL_PUBLICATION}) : {nb_eligibles}")
    print(f"Publies apres validation : {len(cures)}")
    print(f"Transmis a l'archive (score < {SEUIL_PUBLICATION}) : {len(candidats_archives)}")
    print(f"Redaction : {FOURNISSEUR} ({modele_actif()})" if LLM_ACTIF else "Redaction : aucune (heuristique seul)")
    if LLM_ACTIF:
        print(f"Resumes rediges et valides par Ollama : {nb_llm}/{len(cures)}")
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
