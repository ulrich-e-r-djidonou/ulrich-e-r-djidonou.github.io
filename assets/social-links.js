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
    markup:
      '<svg class="icon-plein" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>',
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
