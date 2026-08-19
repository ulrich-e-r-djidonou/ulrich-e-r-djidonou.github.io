// Formulaire de contact : soumission directe au navigateur vers Web3Forms.
// La cle "access_key" placee dans le HTML est publique par conception (c'est
// le navigateur du visiteur qui poste directement vers leur API) : elle ne
// donne acces qu'a l'envoi de soumissions vers la boite configuree, jamais
// a l'adresse elle-meme, qui n'apparait nulle part dans le code source.
// Les messages d'etat suivent la langue de la page : le formulaire est le
// meme des deux cotes du site, seul son retour a l'ecran change.
const ETATS_FORMULAIRE = {
  fr: {
    envoi: "Envoi en cours...",
    succes: "Message envoyé, merci. Je réponds généralement sous quelques jours.",
    echecInterne: "Échec de l'envoi",
    echec: "L'envoi a échoué. Écrivez-moi plutôt via LinkedIn.",
  },
  en: {
    envoi: "Sending...",
    succes: "Message sent, thank you. I usually reply within a few days.",
    echecInterne: "Sending failed",
    echec: "Sending failed. Please write to me on LinkedIn instead.",
  },
};

document.addEventListener("DOMContentLoaded", () => {
  const T = ETATS_FORMULAIRE[document.documentElement.lang === "en" ? "en" : "fr"];
  const form = document.getElementById("contact-form");
  if (!form) return;

  const status = form.querySelector(".form-status");
  const submitButton = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    // Champ piege anti-bot : un visiteur humain ne le voit ni ne le remplit.
    if (form.elements.botcheck && form.elements.botcheck.checked) return;

    submitButton.disabled = true;
    status.textContent = T.envoi;
    delete status.dataset.state;

    try {
      const response = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: { Accept: "application/json" },
        body: new FormData(form),
      });
      const result = await response.json();

      if (result.success) {
        status.textContent = T.succes;
        status.dataset.state = "success";
        form.reset();
      } else {
        throw new Error(result.message || T.echecInterne);
      }
    } catch (error) {
      status.textContent = T.echec;
      status.dataset.state = "error";
    } finally {
      submitButton.disabled = false;
    }
  });
});
