// Configuration centrale des liens sociaux. Une icone n'apparait dans le
// rendu que si son URL est non vide : ajouter Bluesky ou Substack plus tard
// se fait uniquement en renseignant la valeur ici, aucune autre modification
// de page n'est necessaire.
const SOCIAL_LINKS = {
  linkedin: "https://www.linkedin.com/in/ulrichdjidonou",
  github: "https://github.com/ulrich-e-r-djidonou",
  x: "https://x.com/UDjidonou",
  bluesky: "",
  substack: "",
  rss: "https://djidonou.com/frontiere/feed.xml",
};

// Adresse courriel jamais ecrite en clair dans le HTML : assemblee au clic.
// Obfuscation legere anti-scraping, pas un chiffrement.
const MAIL_USER = "romariche";
const MAIL_DOMAIN = "gmail.com";

const SOCIAL_ICON_DEFS = [
  {
    key: "linkedin",
    label: "LinkedIn",
    markup: '<span class="social-icon-label">in</span>',
  },
  {
    key: "github",
    label: "GitHub",
    markup: '<span class="social-icon-label">{ }</span>',
  },
  {
    key: "x",
    label: "X",
    markup: '<span class="social-icon-label">X</span>',
  },
  {
    key: "bluesky",
    label: "Bluesky",
    markup: '<span class="social-icon-label">bs</span>',
  },
  {
    key: "substack",
    label: "Substack",
    markup: '<span class="social-icon-label">su</span>',
  },
  {
    key: "rss",
    label: "Flux RSS de La Frontiere",
    markup:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5c7.732 0 14 6.268 14 14M5 11.5c4.142 0 7.5 3.358 7.5 7.5"/><circle cx="6.2" cy="17.8" r="1.6" fill="currentColor" stroke="none"/></svg>',
  },
];

function renderSocialIcons(root) {
  // insertAdjacentHTML (pas innerHTML) : preserve le bouton "M'ecrire" deja
  // present en dur dans le conteneur, les icones sociales s'ajoutent apres.
  const containers = (root || document).querySelectorAll("[data-social-icons]");
  containers.forEach((container) => {
    const html = SOCIAL_ICON_DEFS.filter((def) => SOCIAL_LINKS[def.key])
      .map((def) => {
        const url = SOCIAL_LINKS[def.key];
        return (
          '<a class="social-icon" href="' +
          url +
          '" aria-label="' +
          def.label +
          '" target="_blank" rel="noopener noreferrer">' +
          def.markup +
          "</a>"
        );
      })
      .join("");
    container.insertAdjacentHTML("beforeend", html);
  });
}

function initMailButtons(root) {
  const buttons = (root || document).querySelectorAll("[data-mail-button]");
  buttons.forEach((button) => {
    button.removeAttribute("hidden");
    button.addEventListener("click", (event) => {
      event.preventDefault();
      window.location.href = "mailto:" + MAIL_USER + "@" + MAIL_DOMAIN;
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  renderSocialIcons(document);
  initMailButtons(document);
});
