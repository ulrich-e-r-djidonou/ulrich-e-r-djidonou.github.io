# Contribuer a ce depot

## Regle de la double langue

Le site existe en deux langues : le francais a la racine, l'anglais sous `en/`.
Toute modification de contenu sur une page francaise entraine la meme
modification sur la page anglaise correspondante, dans le meme commit.

| Francais | Anglais |
| --- | --- |
| `index.html` | `en/index.html` |
| `parcours.html` | `en/career.html` |
| `projets.html` | `en/projects.html` |
| `ressources.html` | `en/resources.html` |
| `faq.html` | `en/faq.html` |
| `contact.html` | `en/contact.html` |
| `frontiere/index.html` | `en/frontier/index.html` |
| `404.html` | `en/404.html` |

Sans cette regle, les deux versions divergent en quelques semaines et la
version anglaise affirme, avec l'autorite d'une page publiee, ce qui n'est plus
vrai cote francais.

Trois points a ne pas oublier en ajoutant ou en deplacant une page :

- Les trois balises `hreflang` (fr, en, x-default) sur chacune des deux pages,
  et le lien `.lang-switch` en fin de navigation, qui pointe vers l'equivalent
  exact et jamais vers la racine de l'autre langue.
- Les deux entrees correspondantes dans `sitemap.xml`, chacune citant les deux
  membres du groupe, elle-meme comprise.
- L'etiquette `.project-langue` sur toute nouvelle carte projet : elle annonce
  la langue du site de destination, y compris quand la reponse est « francais
  seulement ».

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
