"""Valide le balisage schema.org des pages publiees.

Remplace un usage manuel du Google Rich Results Test (qui exige une
authentification Search Console pour un usage scriptable) par un controle
local, exact et executable en CI a chaque publication : chaque bloc
application/ld+json doit etre du JSON bien forme et porter les champs
attendus pour son @type, faute de quoi une page peut se retrouver invisible
ou mal attribuee pour un lecteur automatise sans que rien ne le signale.

Controle uniquement la structure (champs presents, non vides). Ne verifie ni
l'exactitude semantique du contenu, ni ce que Google affiche reellement.

    python -m pipeline.verifier_jsonld
"""

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
PAGES = [RACINE / "index.html", RACINE / "frontiere" / "index.html"]

CHAMPS_REQUIS = {
    "WebSite": ["url", "name"],
    "Person": ["name", "url"],
    "WebPage": ["url", "name"],
    "FAQPage": ["mainEntity"],
    "CollectionPage": ["url", "name"],
    "ItemList": ["itemListElement"],
    "CreativeWork": ["headline", "url", "author", "datePublished", "citation"],
}

MOTIF_BLOC = re.compile(
    r'<script type="application/ld\+json"[^>]*>\s*(.*?)\s*</script>',
    re.DOTALL,
)


def extraire_blocs(chemin):
    contenu = chemin.read_text(encoding="utf-8")
    return MOTIF_BLOC.findall(contenu)


def champ_vide(valeur):
    if valeur is None:
        return True
    if isinstance(valeur, str):
        return valeur.strip() == ""
    if isinstance(valeur, (list, dict)):
        return len(valeur) == 0
    return False


def valider_objet(objet, chemin_logique, erreurs):
    """Verifie un objet schema.org isole (pas ses enfants imbriques)."""
    type_objet = objet.get("@type")
    if not type_objet:
        erreurs.append(f"{chemin_logique} : @type absent")
        return
    requis = CHAMPS_REQUIS.get(type_objet)
    if requis is None:
        return
    for champ in requis:
        if champ not in objet or champ_vide(objet[champ]):
            erreurs.append(f"{chemin_logique} ({type_objet}) : champ '{champ}' absent ou vide")


def valider_creative_work_cite(objet, chemin_logique, erreurs):
    """Regle propre a La Frontiere : la citation doit distinguer le travail
    externe de la redaction du site, sans quoi un lecteur automatise
    attribuerait un papier externe a l'auteur du site."""
    citation = objet.get("citation")
    if not isinstance(citation, dict):
        return
    for champ in ("url", "author"):
        if champ not in citation or champ_vide(citation[champ]):
            erreurs.append(f"{chemin_logique} : citation.{champ} absent ou vide")


def valider_bloc(texte, position, chemin, erreurs):
    prefixe = f"{chemin.name}, bloc {position}"
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as erreur:
        erreurs.append(f"{prefixe} : JSON invalide ({erreur})")
        return

    objets = donnees.get("@graph", [donnees]) if isinstance(donnees, dict) else donnees
    if not isinstance(objets, list):
        objets = [objets]

    for objet in objets:
        if not isinstance(objet, dict):
            continue
        valider_objet(objet, prefixe, erreurs)
        if objet.get("@type") == "ItemList":
            for element in objet.get("itemListElement", []):
                item = element.get("item") if isinstance(element, dict) else None
                if not isinstance(item, dict):
                    erreurs.append(f"{prefixe} : ListItem sans champ 'item' exploitable")
                    continue
                sous_chemin = f"{prefixe} > {item.get('headline', '(sans titre)')}"
                valider_objet(item, sous_chemin, erreurs)
                valider_creative_work_cite(item, sous_chemin, erreurs)


def main():
    erreurs = []
    total_blocs = 0
    for page in PAGES:
        if not page.exists():
            erreurs.append(f"{page} : fichier introuvable")
            continue
        blocs = extraire_blocs(page)
        if not blocs:
            erreurs.append(f"{page.name} : aucun bloc application/ld+json trouve")
            continue
        for position, texte in enumerate(blocs, start=1):
            total_blocs += 1
            valider_bloc(texte, position, page, erreurs)

    if erreurs:
        print(f"Balisage schema.org invalide ({len(erreurs)} probleme(s)) :", file=sys.stderr)
        for erreur in erreurs:
            print(f"  - {erreur}", file=sys.stderr)
        return 1

    print(f"Balisage schema.org valide : {total_blocs} bloc(s) sur {len(PAGES)} page(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
