// Formulaire de contact : soumission directe au navigateur vers Web3Forms.
// La cle "access_key" placee dans le HTML est publique par conception (c'est
// le navigateur du visiteur qui poste directement vers leur API) : elle ne
// donne acces qu'a l'envoi de soumissions vers la boite configuree, jamais
// a l'adresse elle-meme, qui n'apparait nulle part dans le code source.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("contact-form");
  if (!form) return;

  const status = form.querySelector(".form-status");
  const submitButton = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    // Champ piege anti-bot : un visiteur humain ne le voit ni ne le remplit.
    if (form.elements.botcheck && form.elements.botcheck.checked) return;

    submitButton.disabled = true;
    status.textContent = "Envoi en cours...";
    delete status.dataset.state;

    try {
      const response = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: { Accept: "application/json" },
        body: new FormData(form),
      });
      const result = await response.json();

      if (result.success) {
        status.textContent = "Message envoyé, merci. Je réponds généralement sous quelques jours.";
        status.dataset.state = "success";
        form.reset();
      } else {
        throw new Error(result.message || "Échec de l'envoi");
      }
    } catch (error) {
      status.textContent = "L'envoi a échoué. Écrivez-moi plutôt via LinkedIn.";
      status.dataset.state = "error";
    } finally {
      submitButton.disabled = false;
    }
  });
});
