# Contribuer a ce depot

## Verification HTML avant chaque commit

Ce depot fournit un hook `pre-commit` qui verifie la structure des pages
HTML modifiees (balises non fermees, apostrophes courbes, esperluettes non
echappees) avant de laisser passer un commit. Le meme controle tourne dans
le CI (`.github/workflows/tests.yml`), mais l'avoir en local evite un
aller-retour inutile.

A activer une seule fois par clone local :

```sh
git config core.hooksPath .githooks
```

Cette commande dit a Git d'utiliser le dossier `.githooks/` (verse dans le
depot) plutot que le dossier local `.git/hooks/` (jamais synchronise). Elle
reste active pour toutes les commandes `git commit` futures dans ce clone,
sans rien a refaire.
