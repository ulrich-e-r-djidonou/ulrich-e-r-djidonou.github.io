"""Redige le corps de la notification des items publies par une execution.

Le cron de La Frontiere ne signalait rien quand tout se passait bien : seul
un echec faisait remonter une notification GitHub. Ulrich apprenait donc les
publications en visitant le site. Ce module produit le fichier que le
workflow transforme en issue assignee, ce qui fait sonner l'application
GitHub sur son telephone avec les liens.

La liste des items publies se lit en croisant deux fichiers : la recolte
redigee du jour (_candidats_cures.json) et le flux apres publication. Un
candidat redige mais absent du flux a ete archive faute de score, ou a
ete ecarte pour un lien mort : le notifier ferait annoncer une publication
qui n'a pas eu lieu.

Sort 0 et n'ecrit rien quand il n'y a rien de neuf, pour que le workflow
saute l'etape au lieu d'ouvrir une issue vide.

    python -m pipeline.rendre_notification_publication
"""

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RACINE = Path(__file__).parent.parent
FLUX = RACINE / "frontiere" / "data" / "flux.json"
CURES = Path(__file__).parent / "_candidats_cures.json"
SORTIE = Path(__file__).parent / "_publication_du_jour.md"
PAGE = "https://djidonou.com/frontiere/"
PAGE_EN = "https://djidonou.com/en/frontier/"


def charger(fichier, defaut):
    if not fichier.exists():
        return defaut
    contenu = json.loads(fichier.read_text(encoding="utf-8"))
    return contenu["items"] if isinstance(contenu, dict) else contenu


def items_publies(cures, flux):
    """Candidats rediges qui se retrouvent bien dans le flux publie."""
    par_id = {entree["id"]: entree for entree in flux}
    return [par_id[candidat["id"]] for candidat in cures if candidat["id"] in par_id]


def rendre(items):
    lignes = [f"# La Frontiere : {len(items)} nouvel(le)(s) entree(s)", ""]
    for item in items:
        lignes.append(f"## [{item['titre']}]({item['url']})")
        lignes.append("")
        lignes.append(f"{item.get('source', '')}, {item.get('date_publication', '')}")
        lignes.append("")
        resume = item.get("resume_fr", "").strip()
        if resume:
            lignes.append(resume)
            lignes.append("")
        angle = item.get("angle_eco", "").strip()
        if angle:
            lignes.append(f"Enjeu economique : {angle}")
            lignes.append("")
    lignes.append(f"Page francaise : {PAGE}")
    lignes.append("")
    lignes.append(f"Page anglaise : {PAGE_EN}")
    lignes.append("")
    return "\n".join(lignes)


def main():
    items = items_publies(charger(CURES, []), charger(FLUX, []))
    if not items:
        print("Rien de nouveau a notifier.")
        if SORTIE.exists():
            SORTIE.unlink()
        return 0

    SORTIE.write_text(rendre(items), encoding="utf-8")
    print(f"{len(items)} item(s) a notifier, ecrits dans {SORTIE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
