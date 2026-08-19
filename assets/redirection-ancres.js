// Anciennes ancres de la version une-page : redirection vers la page dediee.
// Vivait en script inline dans le <head> de index.html ; sorti ici pour que
// la Content-Security-Policy puisse refuser tout script inline, ce qui est
// precisement la protection qui neutralise une injection dans une page.
//
// Charge sans defer, toujours dans le <head> : la redirection doit partir
// avant que la page s'affiche, sinon le visiteur voit brievement l'accueil
// avant d'etre deplace.
//
// Le meme fichier sert les deux accueils. Sans distinction de langue, un
// visiteur arrivant sur /en/#experience se retrouvait sur la page francaise
// /parcours.html : la redirection annulait le choix de langue qu'il venait
// de faire.
(function () {
  var redirections = {
    fr: {
      "#experience": "/parcours.html#experience",
      "#methode": "/parcours.html#methode",
      "#projets": "/projets.html#projets",
      "#contact": "/contact.html",
    },
    // Les cles restent les anciennes ancres francaises de la version une-page,
    // seule forme qui a jamais circule. Les cibles, elles, portent les id
    // reellement presents dans les pages anglaises (#method, #projects).
    en: {
      "#experience": "/en/career.html#experience",
      "#methode": "/en/career.html#method",
      "#projets": "/en/projects.html#projects",
      "#contact": "/en/contact.html",
    },
  };
  // Le chemin fait foi plutot que l'attribut lang : le script part avant que
  // la page soit rendue, et le chemin est deja connu a cet instant.
  var langue = window.location.pathname.indexOf("/en/") === 0 ? "en" : "fr";
  var cible = redirections[langue][window.location.hash];
  if (cible) {
    window.location.replace(cible);
  }
})();
