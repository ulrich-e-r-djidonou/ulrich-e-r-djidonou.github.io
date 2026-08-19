(function () {
  "use strict";

  // Ce fichier sert deux pages : /frontiere/ (fr) et /en/frontier/ (en).
  // La langue se lit sur <html lang>, jamais sur l'URL : une page deplacee
  // continue d'afficher la bonne langue. Tout ce qui suit est un libelle
  // d'interface ; les donnees, elles, viennent de flux.json.
  const LANG = document.documentElement.lang === "en" ? "en" : "fr";

  // Les donnees vivent sous /frontiere/ quelle que soit la page qui les lit :
  // chemin absolu obligatoire, sinon la page anglaise irait chercher
  // /en/frontier/data/flux.json, qui n'existe pas.
  const BASE_DONNEES = "/frontiere/data/";

  const NOMS_THEMES_PAR_LANGUE = {
    fr: {
      "inference-causale": "Inférence causale",
      "llm": "LLM",
      "prevision": "Prévision",
      "travail-emploi": "Travail et emploi",
      "politique-publique": "Politique publique",
      "outils-recherche": "Outils de recherche",
      "donnees": "Données",
      "macro-finance": "Macro et finance",
    },
    en: {
      "inference-causale": "Causal inference",
      "llm": "LLM",
      "prevision": "Forecasting",
      "travail-emploi": "Labor and employment",
      "politique-publique": "Public policy",
      "outils-recherche": "Research tools",
      "donnees": "Data",
      "macro-finance": "Macro and finance",
    },
  };

  // « Papier » et « Article » ne se distinguaient pas a la lecture. La
  // distinction reelle est le statut de publication, elle est maintenant dans
  // le libelle et definie dans le bloc methode de la page.
  //
  // Les cles restent inchangees : elles vivent dans flux.json et dans toutes
  // les archives mensuelles, les renommer casserait l'affichage des archives
  // et les filtres par type.
  const NOMS_TYPES_PAR_LANGUE = {
    fr: {
      "papier": "Papier de recherche",
      "outil": "Outil",
      "article": "Article publié",
      "dataset": "Dataset",
      "annonce": "Annonce",
      "cours": "Cours",
    },
    en: {
      "papier": "Research paper",
      "outil": "Tool",
      "article": "Published article",
      "dataset": "Dataset",
      "annonce": "Announcement",
      "cours": "Course",
    },
  };

  const NOMS_THEMES = NOMS_THEMES_PAR_LANGUE[LANG];
  const NOMS_TYPES = NOMS_TYPES_PAR_LANGUE[LANG];

  // Libelles d'interface. Les fonctions prennent leurs arguments plutot que
  // d'assembler des morceaux de phrase cote appelant : l'ordre des mots
  // differe d'une langue a l'autre.
  const TEXTES = {
    fr: {
      locale: "fr-CA",
      dateInconnue: "date inconnue",
      par: (auteurs) => `Par ${auteurs}`,
      pourEconomiste: (angle) => `Pour l'économiste : ${angle}`,
      aucuneEntree: "Aucune entrée ne correspond à ces filtres.",
      semaineDu: (semaine) => `Semaine du ${semaine}`,
      semaineRepliee: (semaine, n) =>
        `Semaine du ${semaine} (${n} ${n > 1 ? "entrées" : "entrée"}, cliquer pour voir)`,
      tout: "Tout",
      selectionPrincipale: "Sélection principale",
      archive: (mois) => `Archive ${mois}`,
      boutonArchive: (mois, n) =>
        n ? `${mois} (${n} ${n > 1 ? "entrées" : "entrée"})` : mois,
      aucuneArchive: "Aucune archive pour l'instant.",
      derniereMaj: (date) => `Dernière mise à jour : ${date}`,
      majIndisponible: "Mise à jour indisponible pour le moment.",
      aucunSignal: "Aucun article ne ressort du lot cette semaine.",
      legendeAucunSignal:
        "Les articles collectés depuis la dernière mise à jour touchent aux "
        + "deux thèmes de la veille, économie et intelligence artificielle, "
        + "trop faiblement pour qu'un seul soit mis en avant. La sélection "
        + "complète reste ci-dessous.",
    },
    en: {
      locale: "en-CA",
      dateInconnue: "unknown date",
      par: (auteurs) => `By ${auteurs}`,
      pourEconomiste: (angle) => `For the economist: ${angle}`,
      aucuneEntree: "No entry matches these filters.",
      semaineDu: (semaine) => `Week of ${semaine}`,
      semaineRepliee: (semaine, n) =>
        `Week of ${semaine} (${n} ${n > 1 ? "entries" : "entry"}, click to view)`,
      tout: "All",
      selectionPrincipale: "Main selection",
      archive: (mois) => `Archive ${mois}`,
      boutonArchive: (mois, n) =>
        n ? `${mois} (${n} ${n > 1 ? "entries" : "entry"})` : mois,
      aucuneArchive: "No archive yet.",
      derniereMaj: (date) => `Last updated: ${date}`,
      majIndisponible: "Update unavailable at the moment.",
      aucunSignal: "No article stands out this week.",
      legendeAucunSignal:
        "The articles collected since the last update touch the two themes of "
        + "this monitoring service, economics and artificial intelligence, too "
        + "weakly for a single one to be highlighted. The full selection "
        + "remains below.",
    },
  };

  const T = TEXTES[LANG];

  // Resume et angle economique : la version anglaise est servie quand le
  // pipeline l'a produite, sinon la version francaise prend le relais. Une
  // carte sans texte serait pire qu'une carte dans l'autre langue.
  function resumeDe(entree) {
    return LANG === "en" ? entree.resume_en || entree.resume_fr : entree.resume_fr;
  }

  function angleDe(entree) {
    return LANG === "en" ? entree.angle_eco_en || entree.angle_eco : entree.angle_eco;
  }

  const etat = {
    flux: [],
    themeActif: null,
    typeActif: null,
    recherche: "",
  };

  // Second filet, apres celui de la collecte (pipeline/collect.py,
  // lien_publiable) : les items deja publies dans flux.json ont ete collectes
  // avant que ce filtre existe, et les archives ne sont jamais recollectees.
  // Un href `javascript:` s'execute au clic ; renvoyer null fait afficher le
  // titre sans lien plutot que d'armer le clic.
  function lienSur(url) {
    if (typeof url !== "string") return null;
    try {
      const analysee = new URL(url, window.location.href);
      return analysee.protocol === "http:" || analysee.protocol === "https:"
        ? url
        : null;
    } catch (erreur) {
      return null;
    }
  }

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
    return d.toLocaleDateString(T.locale, { year: "numeric", month: "long", day: "numeric" });
  }

  function debutDeSemaine(iso) {
    if (!iso) return T.dateInconnue;
    const d = new Date(iso + "T00:00:00");
    if (Number.isNaN(d.getTime())) return T.dateInconnue;
    const jour = d.getDay();
    const decalage = (jour + 6) % 7; // lundi = debut de semaine
    d.setDate(d.getDate() - decalage);
    return d.toLocaleDateString(T.locale, { year: "numeric", month: "long", day: "numeric" });
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
    const url = lienSur(entree.url);
    if (url) {
      const lien = document.createElement("a");
      lien.href = url;
      lien.target = "_blank";
      lien.rel = "noopener";
      lien.textContent = entree.titre;
      titre.appendChild(lien);
    } else {
      titre.textContent = entree.titre;
    }
    carte.appendChild(titre);

    // Nom des auteurs affiche des que le champ est fourni (chaine, ex.
    // "Prenom Nom, Prenom Nom") : evite qu'on croie Ulrich Djidonou auteur
    // de l'article relaye.
    if (entree.auteurs) {
      const ligneAuteurs = document.createElement("p");
      ligneAuteurs.className = "carte-auteurs";
      ligneAuteurs.textContent = T.par(entree.auteurs);
      carte.appendChild(ligneAuteurs);
    }

    const texteResume = resumeDe(entree);
    if (texteResume) {
      const resume = document.createElement("p");
      resume.textContent = texteResume;
      carte.appendChild(resume);
    }

    const texteAngle = angleDe(entree);
    if (texteAngle) {
      const angle = document.createElement("p");
      angle.className = "angle-eco";
      angle.textContent = T.pourEconomiste(texteAngle);
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
        const texte = `${e.titre} ${e.resume_fr || ""} ${e.resume_en || ""} ${e.angle_eco || ""} ${e.angle_eco_en || ""}`.toLowerCase();
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
      vide.textContent = T.aucuneEntree;
      conteneur.appendChild(vide);
      return;
    }

    // La semaine la plus recente reste deroulee ; les precedentes sont
    // repliees. Sur 45 entrees reparties sur 8 semaines, tout afficher d'un
    // bloc noyait la selection du jour dans un mur de cartes.
    //
    // « La plus recente » se lit comme le premier groupe rencontre, jamais
    // comme une date en dur : le flux est regenere les lundis et jeudis, une
    // date figee serait fausse des la mise a jour suivante. Apres un filtre,
    // le premier groupe restant s'ouvre aussi, ce qui est le comportement
    // voulu : une recherche ne doit pas renvoyer que des blocs fermes.
    grouperParSemaine(entrees).forEach((groupe, rang) => {
      if (rang === 0) {
        const titreSemaine = document.createElement("h3");
        titreSemaine.className = "semaine-titre";
        titreSemaine.textContent = T.semaineDu(groupe.semaine);
        conteneur.appendChild(titreSemaine);
        groupe.entrees.forEach((entree) => conteneur.appendChild(creerCarte(entree)));
        return;
      }

      const bloc = document.createElement("details");
      bloc.className = "semaine-repliee";
      const resume = document.createElement("summary");
      resume.className = "semaine-titre";
      const nombre = groupe.entrees.length;
      resume.textContent = T.semaineRepliee(groupe.semaine, nombre);
      bloc.appendChild(resume);
      groupe.entrees.forEach((entree) => bloc.appendChild(creerCarte(entree)));
      conteneur.appendChild(bloc);
    });
  }

  function grouperParSemaine(entrees) {
    // Conserve l'ordre d'arrivee des entrees, deja triees par le pipeline :
    // le premier groupe produit est donc bien le plus recent.
    const groupes = [];
    entrees.forEach((entree) => {
      const semaine = debutDeSemaine(entree.date_publication);
      const dernier = groupes[groupes.length - 1];
      if (dernier && dernier.semaine === semaine) {
        dernier.entrees.push(entree);
      } else {
        groupes.push({ semaine, entrees: [entree] });
      }
    });
    return groupes;
  }

  function construireChips(conteneurId, valeurs, noms, cle) {
    const conteneur = document.getElementById(conteneurId);
    conteneur.innerHTML = "";

    const chipTout = document.createElement("button");
    chipTout.className = "chip";
    chipTout.type = "button";
    chipTout.textContent = T.tout;
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

  function afficherJeuEntrees(entrees, titre, archiveActive) {
    etat.flux = entrees || [];
    etat.themeActif = null;
    etat.typeActif = null;
    etat.recherche = "";

    const recherche = document.getElementById("recherche");
    recherche.value = "";
    const themes = Array.from(new Set(etat.flux.flatMap((e) => e.themes || []))).sort();
    const types = Array.from(new Set(etat.flux.map((e) => e.type))).sort();
    construireChips("chips-themes", themes, NOMS_THEMES, "themeActif");
    construireChips("chips-types", types, NOMS_TYPES, "typeActif");

    document.getElementById("flux-titre").textContent = titre;
    document.getElementById("retour-selection").hidden = !archiveActive;
    rendreFlux();
  }

  // Prend la selection principale en argument plutot que etat.flux : celui-ci
  // porte le jeu affiche, archive comprise, et une archive n'a jamais de
  // signal. Sans cet argument, un futur appel depuis une vue d'archive
  // afficherait « aucun article ne ressort cette semaine » a tort.
  function rendreSignal(fluxPrincipal) {
    const signal = fluxPrincipal.find((e) => e.signal);
    const section = document.getElementById("signal-semaine");
    const titre = document.getElementById("signal-titre");
    const legende = document.getElementById("signal-legende");
    if (!signal) {
      // Flux vide : la page entiere est vide, la section n'a rien a dire.
      // Flux garni sans signal : le pipeline a juge que rien n'atteignait le
      // seuil (pipeline/publish.py, SEUIL_SIGNAL). Le dire est plus honnete
      // que de masquer la section, qui laisserait croire a une panne.
      if (fluxPrincipal.length === 0) {
        section.hidden = true;
        return;
      }
      titre.textContent = T.aucunSignal;
      legende.textContent = T.legendeAucunSignal;
      legende.hidden = false;
      section.hidden = false;
      return;
    }
    legende.textContent = "";
    legende.hidden = true;
    titre.textContent = "";
    const url = lienSur(signal.url);
    if (url) {
      const lien = document.createElement("a");
      lien.href = url;
      lien.target = "_blank";
      lien.rel = "noopener";
      lien.textContent = signal.titre;
      titre.appendChild(lien);
    } else {
      titre.textContent = signal.titre;
    }
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

  async function rendreArchives(meta) {
    const conteneur = document.getElementById("liste-archives");
    conteneur.innerHTML = "";
    const mois = (meta && meta.mois_archives) || [];
    if (!mois.length) {
      const vide = document.createElement("p");
      vide.className = "frontiere-vide";
      vide.textContent = T.aucuneArchive;
      conteneur.appendChild(vide);
      return;
    }
    const comptes = (meta && meta.compte_par_archive) || {};
    mois.sort().reverse().forEach((m) => {
      const bouton = document.createElement("button");
      bouton.type = "button";
      // Le compte vient de meta.json quand il y est. Les meta generees avant
      // le 2026-08-12 ne le portent pas : le bouton retombe alors sur le seul
      // mois, plutot que d'afficher un nombre invente.
      const nombre = comptes[m];
      bouton.textContent = T.boutonArchive(m, nombre);
      bouton.addEventListener("click", async () => {
        const archive = await chargerJSON(`${BASE_DONNEES}archives/${m}.json`);
        afficherJeuEntrees(archive, T.archive(m), true);
        document.getElementById("liste-flux").scrollIntoView({ behavior: "smooth" });
      });
      conteneur.appendChild(bouton);
    });
  }

  async function init() {
    const [flux, meta] = await Promise.all([
      chargerJSON(`${BASE_DONNEES}flux.json`),
      chargerJSON(`${BASE_DONNEES}meta.json`),
    ]);

    const fluxPrincipal = flux || [];
    afficherJeuEntrees(fluxPrincipal, T.selectionPrincipale, false);

    const majEl = document.getElementById("derniere-maj");
    majEl.textContent = meta && meta.derniere_mise_a_jour
      ? T.derniereMaj(formaterDate(meta.derniere_mise_a_jour))
      : T.majIndisponible;

    rendreSignal(fluxPrincipal);
    rendreStats(meta);

    document.getElementById("recherche").addEventListener("input", (evt) => {
      etat.recherche = evt.target.value;
      rendreFlux();
    });
    document.getElementById("retour-selection").addEventListener("click", () => {
      afficherJeuEntrees(fluxPrincipal, T.selectionPrincipale, false);
    });

    rendreArchives(meta);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
