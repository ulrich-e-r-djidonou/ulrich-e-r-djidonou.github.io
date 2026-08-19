"""Verifie que les annotations hreflang du site restent reciproques.

Une annotation hreflang unilaterale n'a aucune valeur : un moteur qui ne
retrouve pas l'annotation miroir sur la page pointee peut ignorer la paire
entiere, cote anglais compris. Le site a justement vecu cet etat entre la
publication de /en/ et le present controle : les sept pages anglaises
declaraient leur equivalent francais, aucune page francaise ne declarait
l'inverse.

Controles effectues sur chaque paire FR/EN declaree ci-dessous :
1. Les deux pages existent sur le disque.
2. Chacune porte les trois annotations fr, en et x-default.
3. Les deux pages annoncent exactement les memes URL, et ces URL sont
   bien celles de la paire.
4. x-default pointe vers la version francaise, langue par defaut du site.

    python -m pipeline.verifier_hreflang
"""

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

BASE = "https://djidonou.com"

# fichier francais, fichier anglais, url francaise, url anglaise
PAIRES = (
    ("index.html", "en/index.html", "/", "/en/"),
    ("parcours.html", "en/career.html", "/parcours.html", "/en/career.html"),
    ("projets.html", "en/projects.html", "/projets.html", "/en/projects.html"),
    ("ressources.html", "en/resources.html", "/ressources.html", "/en/resources.html"),
    ("faq.html", "en/faq.html", "/faq.html", "/en/faq.html"),
    ("contact.html", "en/contact.html", "/contact.html", "/en/contact.html"),
    ("frontiere/index.html", "en/frontier/index.html", "/frontiere/", "/en/frontier/"),
)

MOTIF_ALTERNATE = re.compile(
    r'<link\s+rel="alternate"\s+hreflang="([a-zA-Z-]+)"\s+href="([^"]+)"\s*/?>'
)


def annotations(chemin):
    """Renvoie {hreflang: href} pour une page, en ignorant les flux RSS."""
    contenu = chemin.read_text(encoding="utf-8")
    return dict(MOTIF_ALTERNATE.findall(contenu))


def verifier_paire(fichier_fr, fichier_en, url_fr, url_en, racine=RACINE):
    """Renvoie la liste des messages d'anomalie pour une paire FR/EN."""
    anomalies = []
    attendu = {
        "fr": f"{BASE}{url_fr}",
        "en": f"{BASE}{url_en}",
        "x-default": f"{BASE}{url_fr}",
    }

    for fichier in (fichier_fr, fichier_en):
        chemin = racine / fichier
        if not chemin.exists():
            anomalies.append(f"{fichier} : page absente du disque")
            continue

        trouve = annotations(chemin)
        for langue, href in attendu.items():
            if langue not in trouve:
                anomalies.append(f"{fichier} : annotation hreflang='{langue}' absente")
            elif trouve[langue] != href:
                anomalies.append(
                    f"{fichier} : hreflang='{langue}' pointe vers {trouve[langue]}, "
                    f"attendu {href}"
                )

    return anomalies


def main(argv=None):
    anomalies = []
    for paire in PAIRES:
        anomalies.extend(verifier_paire(*paire))

    for message in anomalies:
        print(message)

    if anomalies:
        print(f"\n{len(anomalies)} anomalie(s) sur {len(PAIRES)} paire(s) FR/EN.")
        return 1

    print(f"Annotations hreflang reciproques : {len(PAIRES)} paire(s) FR/EN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
