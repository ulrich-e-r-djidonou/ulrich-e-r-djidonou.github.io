// Filtre la grille de projets par chips (multi-selection, logique OU).
// Aucun chip actif = tous les projets affiches.
document.addEventListener("DOMContentLoaded", () => {
  const chips = document.querySelectorAll("[data-tag-chip]");
  const cartes = document.querySelectorAll("#grille-projets .project-card");
  const messageVide = document.getElementById("grille-projets-vide");

  if (!chips.length || !cartes.length) {
    return;
  }

  function tagsActifs() {
    return Array.from(chips)
      .filter((chip) => chip.getAttribute("aria-pressed") === "true")
      .map((chip) => chip.dataset.tagChip);
  }

  function appliquerFiltre() {
    const actifs = tagsActifs();
    let visibles = 0;

    cartes.forEach((carte) => {
      const tags = (carte.dataset.tags || "").split(" ");
      const correspond = actifs.length === 0 || actifs.some((tag) => tags.includes(tag));
      carte.hidden = !correspond;
      if (correspond) {
        visibles += 1;
      }
    });

    if (messageVide) {
      messageVide.hidden = visibles > 0;
    }
  }

  chips.forEach((chip) => {
    chip.setAttribute("aria-pressed", "false");
    chip.addEventListener("click", () => {
      const actif = chip.getAttribute("aria-pressed") === "true";
      chip.setAttribute("aria-pressed", actif ? "false" : "true");
      appliquerFiltre();
    });
  });
});
