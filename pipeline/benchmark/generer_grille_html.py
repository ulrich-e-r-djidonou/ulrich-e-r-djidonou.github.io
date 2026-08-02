"""Construit une grille de lecture a l'aveugle a partir de evaluation_aveugle.csv.

Le CSV est exploitable dans un tableur, mais noter trente blocs de texte long
dans des cellules est penible et pousse a survoler. Cette grille presente un
item a la fois, les trois versions cote a cote, et enregistre les notes dans
le navigateur. Elle n'embarque pas la cle des modeles : l'aveugle tient meme
si le fichier est ouvert par curiosite.

    python -m pipeline.benchmark.generer_grille_html
    puis ouvrir pipeline/benchmark/evaluation_aveugle.html

Une fois les notes exportees, depouiller avec :
    python -m pipeline.benchmark.depouiller_evaluation notes_aveugle.csv
"""

import csv
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ICI = Path(__file__).parent
SOURCE = ICI / "evaluation_aveugle.csv"
SORTIE = ICI / "evaluation_aveugle.html"

GABARIT = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evaluation a l'aveugle des modeles</title>
<style>
  :root {
    --encre: #16181d;
    --papier: #fbfaf8;
    --trait: #d9d5cd;
    --appui: #7a736a;
    --accent: #1f4b63;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 2rem 1.25rem 5rem;
    background: var(--papier);
    color: var(--encre);
    font: 16px/1.6 Georgia, "Times New Roman", serif;
  }
  main { max-width: 1180px; margin: 0 auto; }
  h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
  .consigne { color: var(--appui); font-size: 0.9rem; max-width: 62ch; }
  .barre {
    position: sticky; top: 0; z-index: 2;
    display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center;
    margin: 1.5rem 0; padding: 0.75rem 0;
    background: var(--papier); border-bottom: 1px solid var(--trait);
    font-family: system-ui, sans-serif; font-size: 0.85rem;
  }
  button {
    font: inherit; padding: 0.4rem 0.9rem; cursor: pointer;
    background: #fff; color: var(--encre);
    border: 1px solid var(--trait); border-radius: 3px;
  }
  button:hover { border-color: var(--accent); color: var(--accent); }
  button.primaire { background: var(--accent); color: #fff; border-color: var(--accent); }
  .avancement { margin-left: auto; color: var(--appui); }
  .titre-item {
    font-size: 1.05rem; font-weight: normal; font-style: italic;
    margin: 0 0 1.25rem; padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--trait);
  }
  .versions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.25rem; }
  @media (max-width: 900px) { .versions { grid-template-columns: 1fr; } }
  .version { border: 1px solid var(--trait); border-radius: 4px; padding: 1rem; background: #fff; }
  .version.notee { border-color: var(--accent); }
  .etiquette {
    font-family: system-ui, sans-serif; font-size: 0.7rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--appui); margin-bottom: 0.6rem;
  }
  .resume { margin: 0 0 0.85rem; }
  .angle { margin: 0 0 1rem; padding-left: 0.75rem; border-left: 2px solid var(--trait); color: #3c4048; }
  .notes { display: flex; gap: 0.35rem; margin-bottom: 0.6rem; }
  .notes button { flex: 1; padding: 0.35rem 0; font-family: system-ui, sans-serif; }
  .notes button[aria-pressed="true"] { background: var(--accent); color: #fff; border-color: var(--accent); }
  textarea {
    width: 100%; min-height: 3.5rem; padding: 0.5rem; resize: vertical;
    font: 0.85rem/1.5 system-ui, sans-serif;
    border: 1px solid var(--trait); border-radius: 3px; background: var(--papier);
  }
  .fin { margin-top: 2rem; font-family: system-ui, sans-serif; font-size: 0.85rem; color: var(--appui); }
</style>
</head>
<body>
<main>
  <h1>Evaluation a l'aveugle des modeles</h1>
  <p class="consigne">
    Trois redactions du meme article, produites par trois modeles differents,
    dans un ordre tire au sort a chaque item. Notez de 1 a 5 la qualite du
    francais et l'interet de l'analyse. La cle des modeles n'est pas dans
    cette page. Les notes restent dans ce navigateur jusqu'a l'export.
  </p>

  <div class="barre">
    <button id="precedent">Precedent</button>
    <button id="suivant" class="primaire">Suivant</button>
    <button id="exporter">Exporter les notes</button>
    <button id="effacer">Effacer</button>
    <span class="avancement" id="avancement"></span>
  </div>

  <h2 class="titre-item" id="titre"></h2>
  <div class="versions" id="versions"></div>
  <p class="fin" id="fin"></p>
</main>

<script>
const DONNEES = __DONNEES__;
const CLE_STOCKAGE = "frontiere-evaluation-aveugle";
const items = Object.keys(DONNEES);
let rang = 0;

// Ouverte par double-clic, la page a une origine file:// et le navigateur peut
// refuser le stockage local. Les notes restent alors en memoire : la page
// fonctionne, mais il faut exporter avant de la fermer.
let stockageDisponible = true;
try {
  localStorage.setItem(CLE_STOCKAGE + "-test", "1");
  localStorage.removeItem(CLE_STOCKAGE + "-test");
} catch (erreur) {
  stockageDisponible = false;
}

let notes = {};
if (stockageDisponible) {
  try {
    notes = JSON.parse(localStorage.getItem(CLE_STOCKAGE) || "{}");
  } catch (erreur) {
    notes = {};
  }
}

function ecrireStockage() {
  if (!stockageDisponible) return;
  try {
    localStorage.setItem(CLE_STOCKAGE, JSON.stringify(notes));
  } catch (erreur) {
    stockageDisponible = false;
  }
}

function sauvegarder() {
  ecrireStockage();
  majAvancement();
}

function majAvancement() {
  const attendu = items.length * 3;
  const faites = Object.values(notes).filter((n) => n && n.note).length;
  const alerte = stockageDisponible
    ? ""
    : " — notes en memoire seulement, exporter avant de fermer";
  document.getElementById("avancement").textContent =
    `Item ${rang + 1} sur ${items.length}, ${faites} version(s) notee(s) sur ${attendu}${alerte}`;
}

function rendre() {
  const item = items[rang];
  const bloc = DONNEES[item];
  document.getElementById("titre").textContent = `${item}. ${bloc.titre}`;

  const conteneur = document.getElementById("versions");
  conteneur.innerHTML = "";
  bloc.versions.forEach((version) => {
    const clef = `${item}|${version.option}`;
    const enregistre = notes[clef] || { note: "", commentaire: "" };

    const carte = document.createElement("div");
    carte.className = "version" + (enregistre.note ? " notee" : "");

    const etiquette = document.createElement("div");
    etiquette.className = "etiquette";
    etiquette.textContent = `Version ${version.option}`;
    carte.appendChild(etiquette);

    const resume = document.createElement("p");
    resume.className = "resume";
    resume.textContent = version.resume_fr;
    carte.appendChild(resume);

    const angle = document.createElement("p");
    angle.className = "angle";
    angle.textContent = version.angle_eco;
    carte.appendChild(angle);

    const notation = document.createElement("div");
    notation.className = "notes";
    [1, 2, 3, 4, 5].forEach((valeur) => {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.textContent = valeur;
      bouton.setAttribute("aria-pressed", String(Number(enregistre.note) === valeur));
      bouton.addEventListener("click", () => {
        notes[clef] = { ...(notes[clef] || {}), note: valeur };
        sauvegarder();
        rendre();
      });
      notation.appendChild(bouton);
    });
    carte.appendChild(notation);

    const commentaire = document.createElement("textarea");
    commentaire.placeholder = "Commentaire libre";
    commentaire.value = enregistre.commentaire || "";
    commentaire.addEventListener("input", (evenement) => {
      notes[clef] = { ...(notes[clef] || {}), commentaire: evenement.target.value };
      ecrireStockage();
    });
    carte.appendChild(commentaire);

    conteneur.appendChild(carte);
  });

  majAvancement();
}

function exporter() {
  const lignes = [["item", "option", "note_humaine_1_5", "commentaire"]];
  items.forEach((item) => {
    DONNEES[item].versions.forEach((version) => {
      const enregistre = notes[`${item}|${version.option}`] || {};
      lignes.push([
        item,
        version.option,
        enregistre.note || "",
        (enregistre.commentaire || "").replace(/"/g, '""'),
      ]);
    });
  });
  const csv = lignes
    .map((ligne) => ligne.map((cellule) => `"${cellule}"`).join(","))
    .join("\\n");
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(new Blob(["\\ufeff" + csv], { type: "text/csv" }));
  lien.download = "notes_aveugle.csv";
  lien.click();
  document.getElementById("fin").textContent =
    "Notes exportees. Depouiller avec : python -m pipeline.benchmark.depouiller_evaluation notes_aveugle.csv";
}

document.getElementById("suivant").addEventListener("click", () => {
  rang = Math.min(rang + 1, items.length - 1);
  rendre();
  window.scrollTo({ top: 0 });
});
document.getElementById("precedent").addEventListener("click", () => {
  rang = Math.max(rang - 1, 0);
  rendre();
  window.scrollTo({ top: 0 });
});
document.getElementById("exporter").addEventListener("click", exporter);
document.getElementById("effacer").addEventListener("click", () => {
  notes = {};
  sauvegarder();
  rendre();
});

rendre();
</script>
</body>
</html>
"""


def construire_donnees():
    donnees = {}
    with SOURCE.open(encoding="utf-8-sig", newline="") as fichier:
        for ligne in csv.DictReader(fichier):
            item = donnees.setdefault(
                ligne["item"], {"titre": ligne["titre"], "versions": []}
            )
            item["versions"].append({
                "option": ligne["option"],
                "resume_fr": ligne["resume_fr"],
                "angle_eco": ligne["angle_eco"],
            })
    return donnees


def main():
    donnees = construire_donnees()
    SORTIE.write_text(
        GABARIT.replace("__DONNEES__", json.dumps(donnees, ensure_ascii=False)),
        encoding="utf-8",
    )
    versions = sum(len(item["versions"]) for item in donnees.values())
    print(f"{len(donnees)} items, {versions} versions.")
    print(f"Grille ecrite dans {SORTIE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
