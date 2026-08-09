/* Rendu de la page Ressources. Reprend le rendu par accordeons qui vivait
   dans frontiere/frontiere.js : les ressources ont quitte La Frontiere pour
   une page dediee, mais le format de donnees (data/bibliotheque.json) et le
   markup (.accordeon) restent les memes. */
(function () {
  "use strict";

  async function chargerJSON(chemin) {
    try {
      const reponse = await fetch(chemin, { cache: "no-store" });
      if (!reponse.ok) return null;
      return await reponse.json();
    } catch (erreur) {
      return null;
    }
  }

  function rendreRessources(items) {
    const conteneur = document.getElementById("accordeons-ressources");
    conteneur.innerHTML = "";
    if (!items || !items.length) {
      const vide = document.createElement("p");
      vide.className = "ressources-vide";
      vide.textContent = "Les ressources ne sont pas disponibles pour le moment.";
      conteneur.appendChild(vide);
      return;
    }

    const parCategorie = new Map();
    items.forEach((item) => {
      if (!parCategorie.has(item.categorie)) parCategorie.set(item.categorie, []);
      parCategorie.get(item.categorie).push(item);
    });

    parCategorie.forEach((liste, categorie) => {
      const details = document.createElement("details");
      details.className = "accordeon";
      const summary = document.createElement("summary");
      summary.textContent = `${categorie} (${liste.length})`;
      details.appendChild(summary);

      const contenu = document.createElement("div");
      contenu.className = "accordeon-contenu";
      liste.forEach((item) => {
        const bloc = document.createElement("div");
        bloc.className = "item-bibliotheque";
        const lien = document.createElement("a");
        lien.href = item.url;
        // Une ressource hebergee sur le site (ex. un PDF sous /assets) reste
        // dans l'onglet courant ; seuls les liens externes s'ouvrent a part.
        if (!item.url.startsWith("/")) {
          lien.target = "_blank";
          lien.rel = "noopener";
        }
        lien.textContent = item.titre;
        bloc.appendChild(lien);
        const description = document.createElement("p");
        description.textContent = item.description_fr;
        bloc.appendChild(description);
        contenu.appendChild(bloc);
      });
      details.appendChild(contenu);
      conteneur.appendChild(details);
    });
  }

  async function init() {
    const ressources = await chargerJSON("/data/bibliotheque.json");
    rendreRessources(ressources);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
