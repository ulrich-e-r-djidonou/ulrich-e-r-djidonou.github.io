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
      // Sans repli sur entrees[0] : depuis le 17 aout 2026 le pipeline peut
      // ne designer aucun signal quand rien n'atteint le seuil (voir
      // pipeline/publish.py, SEUIL_SIGNAL). Presenter alors le dernier
      // article collecte comme « dernier signal » lui prete une importance
      // que la selection lui refuse. La ligne reste masquee, la carte tient
      // sans elle.
      const signal = entrees.find((entree) => entree.signal === true);
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
