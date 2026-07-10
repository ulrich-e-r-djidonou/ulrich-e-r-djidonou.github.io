(function () {
  "use strict";

  const NOMS_THEMES = {
    "inference-causale": "Inférence causale",
    "llm": "LLM",
    "prevision": "Prévision",
    "travail-emploi": "Travail et emploi",
    "politique-publique": "Politique publique",
    "outils-recherche": "Outils de recherche",
    "donnees": "Données",
    "macro-finance": "Macro et finance",
  };

  const NOMS_TYPES = {
    "papier": "Papier",
    "outil": "Outil",
    "article": "Article",
    "dataset": "Dataset",
    "annonce": "Annonce",
    "cours": "Cours",
  };

  const etat = {
    flux: [],
    themeActif: null,
    typeActif: null,
    recherche: "",
  };

  async function chargerJSON(chemin) {
    try {
      const reponse = await fetch(chemin, { cache: "no-store" });
      if (!reponse.ok) return null;
      return await reponse.json();
    } catch (erreur) {
      return null;
    }
  }

  function formaterDate(iso) {
    if (!iso) return "";
    const d = new Date(iso + "T00:00:00");
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleDateString("fr-CA", { year: "numeric", month: "long", day: "numeric" });
  }

  function debutDeSemaine(iso) {
    if (!iso) return "date inconnue";
    const d = new Date(iso + "T00:00:00");
    if (Number.isNaN(d.getTime())) return "date inconnue";
    const jour = d.getDay();
    const decalage = (jour + 6) % 7; // lundi = debut de semaine
    d.setDate(d.getDate() - decalage);
    return d.toLocaleDateString("fr-CA", { year: "numeric", month: "long", day: "numeric" });
  }

  function creerCarte(entree) {
    const carte = document.createElement("article");
    carte.className = "carte-entree";

    const entete = document.createElement("div");
    entete.className = "carte-entete";
    const badge = document.createElement("span");
    badge.className = "badge-type";
    badge.textContent = NOMS_TYPES[entree.type] || entree.type;
    entete.appendChild(badge);
    const sourceEtDate = document.createElement("span");
    sourceEtDate.textContent = `${entree.source} · ${formaterDate(entree.date_publication)}`;
    entete.appendChild(sourceEtDate);
    carte.appendChild(entete);

    const titre = document.createElement("h3");
    const lien = document.createElement("a");
    lien.href = entree.url;
    lien.target = "_blank";
    lien.rel = "noopener";
    lien.textContent = entree.titre;
    titre.appendChild(lien);
    carte.appendChild(titre);

    if (entree.resume_fr) {
      const resume = document.createElement("p");
      resume.textContent = entree.resume_fr;
      carte.appendChild(resume);
    }

    if (entree.angle_eco) {
      const angle = document.createElement("p");
      angle.className = "angle-eco";
      angle.textContent = `Pour l'économiste : ${entree.angle_eco}`;
      carte.appendChild(angle);
    }

    if (entree.themes && entree.themes.length) {
      const tags = document.createElement("div");
      tags.className = "carte-tags";
      entree.themes.forEach((theme) => {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = NOMS_THEMES[theme] || theme;
        tags.appendChild(tag);
      });
      carte.appendChild(tags);
    }

    return carte;
  }

  function filtrerFlux() {
    const q = etat.recherche.trim().toLowerCase();
    return etat.flux.filter((e) => {
      if (etat.themeActif && !(e.themes || []).includes(etat.themeActif)) return false;
      if (etat.typeActif && e.type !== etat.typeActif) return false;
      if (q) {
        const texte = `${e.titre} ${e.resume_fr || ""} ${e.angle_eco || ""}`.toLowerCase();
        if (!texte.includes(q)) return false;
      }
      return true;
    });
  }

  function rendreFlux() {
    const conteneur = document.getElementById("liste-flux");
    conteneur.innerHTML = "";
    const entrees = filtrerFlux();

    if (!entrees.length) {
      const vide = document.createElement("p");
      vide.className = "frontiere-vide";
      vide.textContent = "Aucune entrée ne correspond à ces filtres.";
      conteneur.appendChild(vide);
      return;
    }

    let semaineCourante = null;
    entrees.forEach((entree) => {
      const semaine = debutDeSemaine(entree.date_publication);
      if (semaine !== semaineCourante) {
        semaineCourante = semaine;
        const titreSemaine = document.createElement("h3");
        titreSemaine.className = "semaine-titre";
        titreSemaine.textContent = `Semaine du ${semaine}`;
        conteneur.appendChild(titreSemaine);
      }
      conteneur.appendChild(creerCarte(entree));
    });
  }

  function construireChips(conteneurId, valeurs, noms, cle) {
    const conteneur = document.getElementById(conteneurId);
    conteneur.innerHTML = "";

    const chipTout = document.createElement("button");
    chipTout.className = "chip";
    chipTout.type = "button";
    chipTout.textContent = "Tout";
    chipTout.setAttribute("aria-pressed", "true");
    chipTout.addEventListener("click", () => {
      etat[cle] = null;
      Array.from(conteneur.children).forEach((c) => c.setAttribute("aria-pressed", "false"));
      chipTout.setAttribute("aria-pressed", "true");
      rendreFlux();
    });
    conteneur.appendChild(chipTout);

    valeurs.forEach((valeur) => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.type = "button";
      chip.textContent = noms[valeur] || valeur;
      chip.setAttribute("aria-pressed", "false");
      chip.addEventListener("click", () => {
        etat[cle] = valeur;
        Array.from(conteneur.children).forEach((c) => c.setAttribute("aria-pressed", "false"));
        chip.setAttribute("aria-pressed", "true");
        rendreFlux();
      });
      conteneur.appendChild(chip);
    });
  }

  function rendreSignal() {
    const signal = etat.flux.find((e) => e.signal);
    const section = document.getElementById("signal-semaine");
    if (!signal) {
      section.hidden = true;
      return;
    }
    const titre = document.getElementById("signal-titre");
    titre.innerHTML = "";
    const lien = document.createElement("a");
    lien.href = signal.url;
    lien.target = "_blank";
    lien.rel = "noopener";
    lien.textContent = signal.titre;
    titre.appendChild(lien);
    section.hidden = false;
  }

  function rendreStats(meta) {
    const conteneur = document.getElementById("barres-themes");
    conteneur.innerHTML = "";
    if (!meta || !meta.compte_par_theme) return;

    const entrees = Object.entries(meta.compte_par_theme);
    const max = Math.max(1, ...entrees.map(([, n]) => n));

    entrees.forEach(([theme, n]) => {
      const ligne = document.createElement("div");
      ligne.className = "barre-theme";

      const nom = document.createElement("span");
      nom.textContent = NOMS_THEMES[theme] || theme;
      ligne.appendChild(nom);

      const piste = document.createElement("div");
      piste.className = "barre-theme-piste";
      const remplissage = document.createElement("div");
      remplissage.className = "barre-theme-remplissage";
      remplissage.style.width = `${(n / max) * 100}%`;
      piste.appendChild(remplissage);
      ligne.appendChild(piste);

      const valeur = document.createElement("span");
      valeur.className = "barre-theme-valeur";
      valeur.textContent = String(n);
      ligne.appendChild(valeur);

      conteneur.appendChild(ligne);
    });
  }

  function rendreBibliotheque(items) {
    const conteneur = document.getElementById("accordeons-bibliotheque");
    conteneur.innerHTML = "";
    if (!items || !items.length) {
      const vide = document.createElement("p");
      vide.className = "frontiere-vide";
      vide.textContent = "La bibliothèque n'est pas encore disponible.";
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
        lien.target = "_blank";
        lien.rel = "noopener";
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

  async function rendreArchives(meta) {
    const conteneur = document.getElementById("liste-archives");
    conteneur.innerHTML = "";
    const mois = (meta && meta.mois_archives) || [];
    if (!mois.length) {
      const vide = document.createElement("p");
      vide.className = "frontiere-vide";
      vide.textContent = "Aucune archive pour l'instant.";
      conteneur.appendChild(vide);
      return;
    }
    mois.sort().reverse().forEach((m) => {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.textContent = m;
      bouton.addEventListener("click", async () => {
        const archive = await chargerJSON(`data/archives/${m}.json`);
        etat.flux = archive || [];
        etat.themeActif = null;
        etat.typeActif = null;
        rendreFlux();
        document.getElementById("liste-flux").scrollIntoView({ behavior: "smooth" });
      });
      conteneur.appendChild(bouton);
    });
  }

  async function init() {
    const [flux, meta, bibliotheque] = await Promise.all([
      chargerJSON("data/flux.json"),
      chargerJSON("data/meta.json"),
      chargerJSON("data/bibliotheque.json"),
    ]);

    etat.flux = flux || [];

    const majEl = document.getElementById("derniere-maj");
    majEl.textContent = meta && meta.derniere_mise_a_jour
      ? `Dernière mise à jour : ${formaterDate(meta.derniere_mise_a_jour)}`
      : "Mise à jour indisponible pour le moment.";

    rendreSignal();
    rendreStats(meta);

    const themes = Array.from(new Set(etat.flux.flatMap((e) => e.themes || []))).sort();
    const types = Array.from(new Set(etat.flux.map((e) => e.type))).sort();
    construireChips("chips-themes", themes, NOMS_THEMES, "themeActif");
    construireChips("chips-types", types, NOMS_TYPES, "typeActif");

    document.getElementById("recherche").addEventListener("input", (evt) => {
      etat.recherche = evt.target.value;
      rendreFlux();
    });

    rendreFlux();
    rendreBibliotheque(bibliotheque);
    rendreArchives(meta);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
