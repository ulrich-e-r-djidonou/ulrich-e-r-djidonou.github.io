---
name: djidonou.com
description: Site personnel d'un économiste quantitatif, sobre et factuel, sur papier chaud
colors:
  paper: "#f7f4ee"
  ink: "#16201f"
  muted: "#5e6a67"
  teal: "#0b5c5a"
  teal-dark: "#073f3d"
  green: "#7b9e53"
  amber: "#c38a2e"
  line: "#d7d0c3"
  white: "#fffdf8"
  heading: "#073f3d"
  on-accent: "#fffdf8"
  on-teal: "#fffdf8"
  soft-bg: "#eef4ed"
  soft-border: "#bfd0b8"
  soft-text: "#31422c"
typography:
  display:
    fontFamily: "Georgia, 'Times New Roman', serif"
    fontSize: "4.25rem"
    lineHeight: 0.98
    letterSpacing: "0"
  headline:
    fontFamily: "Georgia, 'Times New Roman', serif"
    fontSize: "2.35rem"
    lineHeight: 1.12
  title:
    fontFamily: "Georgia, 'Times New Roman', serif"
    fontSize: "1.45rem"
    lineHeight: 1.15
  body:
    fontFamily: "Georgia, 'Times New Roman', serif"
    fontSize: "1.16rem"
    lineHeight: 1.55
  label:
    fontFamily: "'Trebuchet MS', Verdana, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 700
    letterSpacing: "0.08em"
rounded:
  filet: "2px"
  sm: "4px"
  md: "6px"
  lg: "14px"
  pill: "999px"
components:
  button-primary:
    backgroundColor: "{colors.teal}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.sm}"
    padding: "0.75rem 1.1rem"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.heading}"
    rounded: "{rounded.sm}"
    padding: "0.75rem 1.1rem"
  chip:
    backgroundColor: "{colors.white}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "0.4rem 0.75rem"
  chip-active:
    backgroundColor: "{colors.teal}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.pill}"
  card-project:
    backgroundColor: "{colors.white}"
    rounded: "{rounded.md}"
    padding: "1.35rem"
---

# Design System: djidonou.com

## Overview

**Creative North Star: "Le carnet de terrain"**

Le site est le carnet de terrain d'un économiste : papier chaud, serif classique (Georgia), filets fins de 1px, pastilles de timeline, encadrés factuels. Rien ne crie; la retenue est le style. Le seul geste graphique affirmé est le liseré signature "ligne de frontière", un dégradé teal, vert, ambre qui souligne la navigation active, encadre le portrait, borde le pied de page et coiffe les cartes au survol.

Le système est theme-aware (clair et sombre via `prefers-color-scheme`), avec une famille de tokens `--soft-*` à fond clair fixe qui ne s'inverse jamais (proof-strip, cartes vedettes), pour préserver leur contraste propre.

**Key Characteristics:**
- Papier chaud et serif éditoriale, jamais de look SaaS
- Un seul motif signature : le dégradé "ligne de frontière"
- Filets 1px et pastilles plutôt que bordures épaisses ou cartes lourdes
- Sans-serif (Trebuchet MS) réservée aux étiquettes, navigation, boutons
- Mode sombre natif, tokens à inversion contrôlée

## Colors

Palette de carnet : neutres papier et encre, un teal institutionnel dominant, vert et ambre en appuis rares.

### Primary
- **Teal frontière** (#0b5c5a): accent principal; boutons primaires, liens de carte, pastilles de timeline, kickers. En sombre il s'éclaircit (#4fc7bd).
- **Teal profond** (#073f3d): titres (`--heading` en clair) et fond du bloc Méthode. Reste fixe entre thèmes quand il sert de fond.

### Secondary
- **Vert lichen** (#7b9e53): deuxième teinte du liseré; bordure de carte au survol, filets du bloc Méthode.
- **Ambre carnet** (#c38a2e): troisième teinte du liseré; badges de statut, outline de focus (3px).

### Neutral
- **Papier** (#f7f4ee): fond de page (sombre : #101716).
- **Encre** (#16201f): texte courant (sombre : #e8ece9).
- **Gris terrain** (#5e6a67): texte secondaire et descriptions.
- **Filet** (#d7d0c3): bordures 1px, séparateurs, timeline.
- **Blanc cassé** (#fffdf8): surfaces de cartes et sections alternées.
- **Famille soft** (#eef4ed / #bfd0b8 / #31422c): encadrés à fond clair fixe, jamais inversés par le thème.

### Named Rules
**La règle du liseré.** Le dégradé `linear-gradient(90deg, teal 0%, vert 55%, ambre 100%)` est le seul gradient autorisé du site. Il apparaît en filet fin (2 à 4px) : navigation active, signature-line, bordure du portrait, top de carte au survol, pied de page. Jamais en fond de bloc, jamais en texte.

**La règle du texte sur teal.** `--on-accent` (#fffdf8) ne sert qu'aux fonds qui restent sombres dans les deux thèmes (bloc Méthode sur `--teal-dark`). Tout texte posé sur `--teal`, qui s'éclaircit en sombre (#4fc7bd), utilise `--on-teal` : #fffdf8 en clair, #08201e en sombre. Sans cette bascule, les boutons primaires et les chips actives tombent à 2.0:1 en mode sombre.

**La règle du focus ambre.** Tout élément focusable reçoit `outline: 3px solid var(--amber); outline-offset: 3-4px`. Uniforme sur tout le site.

## Typography

**Display Font:** Georgia (avec Times New Roman, serif)
**Body Font:** Georgia (même famille)
**Label Font:** Trebuchet MS (avec Verdana, sans-serif)

**Character:** serif système classique pour tout le contenu, sans-serif compacte et graissée pour la mécanique (navigation, boutons, étiquettes, dates). Le contraste serif/sans est fonctionnel : lire vs agir.

### Hierarchy
Échelle nommée en tokens `--fs-*`; toute nouvelle taille doit réutiliser un step existant ou en ajouter un documenté ici.

- **Display** (4.25rem / 0.98, `--fs-h1`): titre du hero uniquement; 2.65rem sur mobile. Pages intérieures : 2.9rem (`--fs-h1-page`).
- **Headline** (2.35rem / 1.12, `--fs-h2`): titres de section.
- **Title** (1.45rem, `--fs-title`): titres de carte projet; 1.35rem pour les entrées de parcours.
- **Body** (1.16rem / 1.55, `--fs-base`): texte courant, gris terrain, largeurs max 55-62ch. Chapeau (lead) : 1.28rem.
- **Label** (0.8rem, 700, 0.08em, uppercase, `--fs-2xs`): kickers et étiquettes; navigation à 0.88rem sans uppercase.

### Named Rules
**La règle des steps.** Quinze tailles littérales ont été regroupées en steps nommés; ne jamais réintroduire une taille littérale dans une règle.

## Layout

Sections pleine largeur empilées, padding horizontal 4rem (1.25rem sous 980px), padding vertical 4.5rem (3rem mobile). Alternance de fonds papier / blanc cassé séparés par filets 1px. Grilles : projets en `repeat(3, minmax(0, 1fr))`, méthode en 4 colonnes, tout passe en 1 colonne sous 980px. Header sticky avec backdrop-blur, empilé en colonne sous 620px ; à sept liens la nav ne tient plus sur une seule ligne à une taille lisible, elle se replie donc naturellement sur deux lignes équilibrées (5 + 2 à 390px, 4 + 3 à 320px) plutôt que d'être compressée ou mise en défilement horizontal. Largeurs de lecture plafonnées (34rem lead, 55-56rem sections, 62ch FAQ).

## Elevation & Depth

Système quasi plat : la profondeur vient des fonds alternés et des filets. Les ombres sont ambiantes et douces, réservées aux cartes et au portrait. Survols : translation de -2px (boutons, icônes sociales) ou -4px (cartes), transitions 180ms ease.

### Shadow Vocabulary
- **Carte** (`box-shadow: 0 10px 24px var(--card-shadow)`, alpha 0.08 clair / 0.35 sombre): cartes projet.
- **Portrait** (`0 18px 34px var(--card-shadow)`): image du hero.

### Named Rules
**La règle posée.** Rien ne bouge de plus de 4px, rien ne dure plus de 220ms, aucun rebond. `prefers-reduced-motion` coupe tout à 1ms.

## Shapes

Coins discrets : 4px (boutons, encadrés), 6px (cartes), 14px (portrait), 999px (chips et badges), cercles pour photos et icônes sociales. Bordures toujours 1px sauf le liseré signature (2-4px) et le filet 2px du bloc Méthode. La timeline (parcours, publications) est un filet vertical 1px avec pastilles rondes de 9px, jamais une bordure latérale épaisse.

## Components

### Buttons
- **Shape:** coins doux (4px), min-height 2.85rem, padding 0.75rem 1.1rem, Trebuchet 700 à 0.95rem.
- **Primary:** fond teal, texte blanc cassé (`--on-accent`).
- **Secondary:** transparent, bordure teal 1px, texte heading.
- **Hover / Focus:** translateY(-2px) en 180ms; focus ambre 3px.

### Chips (filtres projets)
- **Style:** pilule (999px), fond blanc cassé, bordure filet, texte gris, Trebuchet 700 à 0.8rem.
- **State:** `aria-pressed="true"` passe fond et bordure en teal, texte en `--on-accent`.

### Cards / Containers
- **Corner Style:** 6px, bordure filet 1px, min-height 270px.
- **Background:** blanc cassé; variante `featured` sur fond soft vert avec textes de la famille soft (non inversés en sombre).
- **Shadow Strategy:** ombre carte ambiante; survol : -4px, bordure verte, liseré signature qui se déploie en haut (scaleX 0 vers 1, 220ms).
- **Thumb:** image 16/9 en pleine largeur de carte (marges négatives).

### Figure de distinction
- **Variante par défaut** (`.distinction-figure`): image verticale de 130px à gauche, légende à droite, filet 1px et coins 6px.
- **Variante large** (`.distinction-figure--wide`): photo paysage en pleine largeur (560px max), légende empilée dessous en colonne. Le premier segment (`__title`) reprend le titre de la source en encre pleine, les segments suivants restent en gris terrain, la ligne source (`__source`) est en italique et porte le lien externe.
- **Règle de citation:** titre, description et légende sont repris mot pour mot de la source institutionnelle; la photo est hébergée localement pour survivre au retrait de la page d'origine.

### Navigation
- **Style:** Trebuchet 0.88rem, gris terrain; page active en heading 700 avec soulignement liseré 2px. Header sticky, fond translucide flouté, filet bas 1px.

### Le liseré (signature)
Filet dégradé teal-vert-ambre décliné en : signature-line du hero (4.5rem x 3px), tiret des kickers (1.6rem x 3px), soulignement de nav active, border-image du portrait et du pied de page, top de carte au survol.

## Do's and Don'ts

### Do:
- **Do** réutiliser les steps `--fs-*` et les tokens de couleur; toute nouveauté passe par `:root` et se documente ici.
- **Do** réserver le liseré aux filets fins; c'est sa rareté qui le rend signature.
- **Do** vérifier chaque ajout dans les deux thèmes; utiliser la famille `--soft-*` pour tout encadré qui ne doit pas s'inverser.
- **Do** garder le focus ambre 3px sur tout élément interactif ajouté.

### Don't:
- **Don't** introduire de bordure latérale épaisse comme accent (l'ancienne timeline 3px a été retirée exprès).
- **Don't** utiliser le dégradé en fond de bloc ou en texte (`background-clip: text` interdit).
- **Don't** ajouter d'autre famille de police ni de taille littérale hors échelle.
- **Don't** dépasser -4px / 220ms sur les survols; aucun rebond, aucune animation décorative.
