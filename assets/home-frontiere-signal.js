// Rend la carte "La Frontiere" de l'accueil vivante : affiche le titre du
// dernier signal detecte par le pipeline. En cas d'echec du fetch (hors
// ligne, JSON absent), la ligne reste simplement masquee ; le reste de la
// carte (texte fixe + lien) fonctionne sans elle, donc rien ne casse.
document.addEventListener("DOMContentLoaded", () => {
  const teaser = document.querySelector("[data-frontiere-signal-teaser]");
  if (!teaser) {
    return;
  }

  fetch("/frontiere/data/flux.json")
    .then((response) => {
      if (!response.ok) {
        throw new Error("reponse non ok");
      }
      return response.json();
    })
    .then((entrees) => {
      if (!Array.isArray(entrees) || entrees.length === 0) {
        return;
      }
      const signal = entrees.find((entree) => entree.signal === true) || entrees[0];
      if (!signal || !signal.titre) {
        return;
      }
      teaser.textContent = "Dernier signal : " + signal.titre;
      teaser.removeAttribute("hidden");
    })
    .catch(() => {
      // Fallback silencieux : la carte reste complete sans la ligne de signal.
    });
});
