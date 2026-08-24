"""Detecte les items de La Frontiere que la page anglaise sert en francais.

publish.py sert le francais en repli quand resume_en manque. Le repli est un
filet, pas un etat acceptable : un lecteur anglophone voit alors du francais
sans que rien ne le signale, et c'est reste ainsi pour 36 items sur 62
jusqu'au 2026-08-24, parce que rien ne mesurait la proportion.

Ce controle compte les items publies sans champs anglais et echoue au-dela
d'un seuil. Un ou deux items en attente ne justifient pas de faire rougir le
cron ; une derive generale, si. Le seuil laisse aussi passer le cas legitime
et irreductible d'un item dont l'abstract d'origine n'est plus recuperable
(pipeline.collecter_abstracts_manquants ne le retrouve pas), pour lequel il
n'y a pas de source anglaise a resumer.

Quand ce controle echoue :

    python -m pipeline.collecter_abstracts_manquants
    python -m pipeline.regenerer_flux --anglais --estimer
    python -m pipeline.regenerer_flux --anglais
    python -m pipeline.regenerer_flux --anglais --depuis-relecture

    python -m pipeline.verifier_bilinguisme_flux
"""

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
FLUX = RACINE / "frontiere" / "data" / "flux.json"

# Part maximale d'items servis en francais sur la page anglaise.
SEUIL_REPLI = 0.10


def items_en_repli(items):
    """Items publies auxquels il manque au moins un des deux champs anglais."""
    return [
        item
        for item in items
        if not item.get("resume_en") or not item.get("angle_eco_en")
    ]


def main():
    if not FLUX.exists():
        print(f"{FLUX} introuvable, rien a verifier.")
        return 0

    items = json.loads(FLUX.read_text(encoding="utf-8"))
    if not items:
        print("Flux vide, rien a verifier.")
        return 0

    manquants = items_en_repli(items)
    part = len(manquants) / len(items)
    print(
        f"Bilinguisme du flux : {len(items) - len(manquants)}/{len(items)} items "
        f"avec resume et angle anglais ({part:.1%} en repli francais)."
    )

    if part <= SEUIL_REPLI:
        return 0

    print("\nServis en francais sur /en/frontier/ :")
    for item in manquants:
        print(f"  - {item.get('titre', item.get('id', ''))}")
    print(
        f"\nAu-dela de {SEUIL_REPLI:.0%}, c'est une derive, pas un item isole. "
        "Lancer le rattrapage anglais : voir l'entete de ce fichier."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
