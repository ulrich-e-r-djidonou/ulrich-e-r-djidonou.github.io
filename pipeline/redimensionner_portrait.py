"""Produit les versions WebP du portrait a partir de assets/ulrich-djidonou-portrait.png.

A relancer seulement si le PNG source change. Pillow n'est pas dans
pipeline/requirements.txt : la CI n'en a pas besoin. En local :
    pip install pillow
    python -m pipeline.redimensionner_portrait

Largeurs produites (la hauteur suit les proportions du PNG) :
    68  : vignette de l'en-tete, affichee en 34 px (double densite)
    136 : photo de la page contact, affichee en 64 px (double densite)
    272 : portrait de l'accueil, affiche en 220 px au plus (simple densite)
    437 : portrait de l'accueil en double densite. C'est la largeur du PNG
          source : l'agrandir a 544 px n'ajouterait aucun detail.
Le PNG reste en place pour le JSON-LD et les liens externes.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).parent.parent
SOURCE = RACINE / "assets" / "ulrich-djidonou-portrait.png"
LARGEURS = (68, 136, 272, 437)
QUALITE = 80


def produire(source=SOURCE, largeurs=LARGEURS, qualite=QUALITE):
    from PIL import Image

    sorties = []
    with Image.open(source) as image:
        image = image.convert("RGB")
        for largeur in largeurs:
            if largeur > image.width:
                raise ValueError(f"{largeur} px depasse la largeur du source ({image.width} px)")
            hauteur = round(image.height * largeur / image.width)
            cible = source.parent / f"portrait-{largeur}.webp"
            image.resize((largeur, hauteur), Image.LANCZOS).save(
                cible, "WEBP", quality=qualite, method=6
            )
            sorties.append((cible, largeur, hauteur, cible.stat().st_size))
    return sorties


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for cible, largeur, hauteur, octets in produire():
        print(f"{cible.name} : {largeur} x {hauteur}, {octets} octets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
