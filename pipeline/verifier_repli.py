"""Verifie que les fournisseurs LLM repondent encore.

Le repli ne sert que lorsque le fournisseur principal tombe ou epuise son
quota, c'est-a-dire quelques fois par an. Sa cle peut donc expirer, etre
revoquee ou avoir ete posee tronquee sans que rien ne le dise : le defaut
n'apparait qu'au pire moment, quand le principal vient de lacher et que le
repli est la seule chose qui separe la veille d'un echec.

C'est arrive : la cle de repli rendait 401 depuis au moins le 24 aout 2026,
et le seul symptome etait un rattrapage anglais qui echouait en entier au
lieu de basculer. Ce controle transforme cette panne silencieuse en signal.

Le principal est verifie de la meme facon. Sa panne se voit plus vite, la
veille echouant des la premiere execution, mais un quota atteint (429) n'est
pas une panne : le controle le distingue et n'echoue pas dessus, sans quoi il
passerait au rouge chaque fois qu'un lot aurait consomme la journee.

Un seul appel, la reponse la plus courte possible : le cout est negligeable
et c'est le point de terminaison lui-meme qu'on veut eprouver, pas le modele.

    python -m pipeline.verifier_repli
"""

import os
import sys

import requests

from . import curate

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Les deux fournisseurs, chacun avec le nom de ses variables : un message qui
# nomme la variable a corriger evite d'avoir a relire le workflow pour savoir
# quel secret reposer.
FOURNISSEURS = {
    "principal": ("LLM_API_URL", "LLM_API_MODELE", "LLM_API_CLE"),
    "repli": ("LLM_API_URL_REPLI", "LLM_API_MODELE_REPLI", "LLM_API_CLE_REPLI"),
}


def verifier(role="repli", url=None, modele=None, cle=None):
    """Retourne (ok, message). N'attend rien du contenu de la reponse.

    Seule compte la capacite du service a repondre : un modele qui rend un
    texte inattendu reste un modele joignable, et c'est la joignabilite qui
    manque quand une cle expire.
    """
    noms = FOURNISSEURS[role]
    if role == "principal":
        defauts = (curate.API_URL, curate.API_MODELE, curate.API_CLE)
    else:
        defauts = (curate.API_URL_REPLI, curate.API_MODELE_REPLI, curate.API_CLE_REPLI)
    url = url if url is not None else defauts[0]
    modele = modele if modele is not None else defauts[1]
    cle = cle if cle is not None else defauts[2]

    if not (url and modele and cle):
        manquantes = [
            nom for nom, valeur in zip(noms, (url, modele, cle)) if not valeur
        ]
        return False, f"Fournisseur {role} non configure : " + ", ".join(manquantes) + "."

    try:
        reponse = curate._requete_api(requests, "Reply with the single word: ok", url, modele, cle)
    except requests.HTTPError as erreur:
        code = erreur.response.status_code if erreur.response is not None else "?"
        if code == 429:
            # Un quota atteint prouve que la cle est acceptee : c'est le
            # fonctionnement normal d'un palier gratuit un jour de gros lot,
            # pas une panne a signaler.
            return True, f"Fournisseur {role} ({modele}) : quota atteint, mais la cle repond."
        indice = {
            401: "cle refusee : expiree, revoquee, ou posee tronquee",
            403: "cle valide mais acces refuse : credits ou droits absents",
            404: "point de terminaison ou modele introuvable",
        }.get(code, "reponse inattendue du service")
        return False, f"Fournisseur {role} ({modele}) : HTTP {code}, {indice}."
    except requests.RequestException as erreur:
        return False, f"Fournisseur {role} ({modele}) injoignable : {erreur}."

    if not reponse:
        return False, f"Fournisseur {role} ({modele}) : reponse vide."
    return True, f"Fournisseur {role} ({modele}) : joignable."


def main():
    # Les deux sont verifies avant de conclure : s'arreter au premier echec
    # cacherait l'etat du second, et c'est justement la combinaison qui
    # compte, un principal casse etant sans consequence tant que le repli
    # tient.
    resultats = [verifier(role) for role in FOURNISSEURS]
    for ok, message in resultats:
        print(message)
    return 0 if all(ok for ok, _ in resultats) else 1


if __name__ == "__main__":
    sys.exit(main())
