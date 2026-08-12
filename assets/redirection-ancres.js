// Anciennes ancres de la version une-page : redirection vers la page dediee.
// Vivait en script inline dans le <head> de index.html ; sorti ici pour que
// la Content-Security-Policy puisse refuser tout script inline, ce qui est
// precisement la protection qui neutralise une injection dans une page.
//
// Charge sans defer, toujours dans le <head> : la redirection doit partir
// avant que la page s'affiche, sinon le visiteur voit brievement l'accueil
// avant d'etre deplace.
(function () {
  var redirections = {
    "#experience": "/parcours.html#experience",
    "#methode": "/parcours.html#methode",
    "#projets": "/projets.html#projets",
    "#contact": "/contact.html",
  };
  var cible = redirections[window.location.hash];
  if (cible) {
    window.location.replace(cible);
  }
})();
