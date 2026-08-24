"""Verifie que le fournisseur de repli repond encore.

Le repli ne sert que lorsque le fournisseur principal tombe ou epuise son
quota, c'est-a-dire quelques fois par an. Sa cle peut donc expirer, etre
revoquee ou avoir ete posee tronquee sans que rien ne le dise : le defaut
n'apparait qu'au pire moment, quand le principal vient de lacher et que le
repli est la seule chose qui separe la veille d'un echec.

C'est arrive : la cle de repli rendait 401 depuis au moins le 24 aout 2026,
et le seul symptome etait un rattrapage anglais qui echouait en entier au
lieu de basculer. Ce controle transforme cette panne silencieuse en signal.

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


def verifier(url=None, modele=None, cle=None):
    """Retourne (ok, message). N'attend rien du contenu de la reponse.

    Seule compte la capacite du service a repondre : un modele qui rend un
    texte inattendu reste un modele joignable, et c'est la joignabilite qui
    manque quand une cle expire.
    """
    url = url if url is not None else curate.API_URL_REPLI
    modele = modele if modele is not None else curate.API_MODELE_REPLI
    cle = cle if cle is not None else curate.API_CLE_REPLI

    if not (url and modele and cle):
        manquantes = [
            nom
            for nom, valeur in (
                ("LLM_API_URL_REPLI", url),
                ("LLM_API_MODELE_REPLI", modele),
                ("LLM_API_CLE_REPLI", cle),
            )
            if not valeur
        ]
        return False, "Repli non configure : " + ", ".join(manquantes) + "."

    try:
        reponse = curate._requete_api(requests, "Reply with the single word: ok", url, modele, cle)
    except requests.HTTPError as erreur:
        code = erreur.response.status_code if erreur.response is not None else "?"
        indice = {
            401: "cle refusee : expiree, revoquee, ou posee tronquee",
            403: "cle valide mais acces refuse : credits ou droits absents",
            404: "point de terminaison ou modele introuvable",
            429: "quota atteint",
        }.get(code, "reponse inattendue du service")
        return False, f"Repli ({modele}) : HTTP {code}, {indice}."
    except requests.RequestException as erreur:
        return False, f"Repli ({modele}) injoignable : {erreur}."

    if not reponse:
        return False, f"Repli ({modele}) : reponse vide."
    return True, f"Repli ({modele}) : joignable."


def main():
    ok, message = verifier()
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
