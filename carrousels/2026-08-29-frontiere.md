# Carrousel La Frontière, 29 août 2026

Statut : PLAN A VALIDER. Aucune conversion en PDF avant accord.
Fil directeur : l'algorithme comme agent économique, pas comme observateur neutre.
Format visé : 9 diapositives carrées (1080 x 1080), PDF LinkedIn.

---

## Diapositive 1, couverture

**Deux papiers, une même leçon : l'algorithme n'est pas un observateur neutre.**

La Frontière, veille du 29 août 2026

---

## Diapositive 2, le signal de la semaine

**Manipulation-Robust Prediction**
Daniel Björkegren, Joshua E. Blumenstock, Samsun Knight, *American Economic Review*, septembre 2026

Un algorithme de ciblage devient public. Les gens apprennent ce qu'il regarde, ajustent ce qu'ils déclarent, et le modèle se dégrade.

Les auteurs construisent des règles de décision qui anticipent cette réaction. Testées lors d'une expérience de terrain au Kenya, ces règles linéaires robustes à la manipulation battent un LASSO standard.

Source : https://doi.org/10.1257/aer.20241087

---

## Diapositive 3, pourquoi ça compte

La prévision suppose d'ordinaire que le monde ne réagit pas à la prévision. Dès qu'une règle attribue une aide, un crédit ou une place en service public, cette hypothèse tombe.

Lucas avait formulé le problème pour la politique macroéconomique. Ce papier le rend opérationnel à l'échelle d'un algorithme d'attribution.

Conséquence pratique : la transparence cesse d'être un coût de performance. La règle tient même une fois publiée.

---

## Diapositive 4, aussi dans la veille

**Pricing with Algorithms**
Rohit Lamba, Sergey Zhuk, *AER: Insights*, septembre 2026

Duopole répété. Chaque vendeur programme un algorithme qui réagit au prix du concurrent.

Sur toute grille de prix finie, tous les équilibres de Markov parfaits sont supraconcurrentiels. Aucune communication entre les vendeurs, aucun accord, et des prix de collusion malgré tout.

Source : https://doi.org/10.1257/aeri.20240436

---

## Diapositive 5, le fil commun

Dans les deux cas, l'agent économique n'est plus seulement la personne. C'est aussi le code qui décide à sa place.

Chez Björkegren et ses coauteurs, la population réagit à l'algorithme.
Chez Lamba et Zhuk, les algorithmes réagissent entre eux.

La théorie des jeux revient par la porte de l'ingénierie logicielle.

---

## Diapositive 6, ce que ça change pour qui décide

Un algorithme d'attribution devrait être évalué sur son comportement une fois publié, pas seulement sur sa performance hors échantillon.

En droit de la concurrence, chercher la preuve d'une entente perd de sa force si l'équilibre supraconcurrentiel n'exige aucune entente.

La question ouverte : réguler l'algorithme, ou l'équilibre qu'il produit ?

---

## Diapositive 7, aussi dans la veille

**Macroeconomic Impacts of China's Energy Transition**
Hugo Rojas-Romagosa, Gregor Schwerhoff, Sneha Thube, Sha Yu, *IMF Working Papers*, août 2026

Le solaire et l'éolien dominent désormais les nouveaux ajouts de capacité électrique en Chine. Le modèle d'équilibre général calculable donne une hausse modérée des prix à court terme, puis des baisses durables, avec un PIB plus élevé et une sécurité énergétique renforcée.

Le stockage par batterie gère mieux la variabilité que le maintien du charbon. La contrepartie est un risque accru d'actifs échoués dans la production charbonnière.

Source : https://doi.org/10.5089/9798229060783.001

---

## Diapositive 8, d'où vient cette veille

La Frontière suit l'intersection entre économie et intelligence artificielle. Collecte automatisée, filtrage par score, rédaction assistée, relecture humaine avant mise en ligne.

68 entrées actives, mise à jour plusieurs fois par semaine.

djidonou.com/frontiere

---

## Diapositive 9, question de clôture

Qu'est-ce qui vous frappe davantage : qu'un algorithme public puisse rester robuste une fois ses critères connus, ou que des algorithmes privés convergent vers des prix de collusion sans jamais se parler ?

---

# Texte du post

Deux papiers publiés cette semaine disent la même chose depuis deux directions opposées.

Björkegren, Blumenstock et Knight (*AER*) montrent qu'un algorithme de ciblage rendu public peut rester performant si on modélise dès le départ la réaction stratégique des personnes concernées. Leur règle bat un LASSO standard sur une expérience de terrain au Kenya.

Lamba et Zhuk (*AER: Insights*) montrent que des algorithmes de prix en duopole convergent vers des tarifs supraconcurrentiels sur toute grille finie, sans aucune communication entre les vendeurs.

D'un côté, les gens réagissent à l'algorithme. De l'autre, les algorithmes réagissent entre eux. Dans les deux cas, traiter le modèle comme un observateur extérieur au système conduit à se tromper.

Le détail dans le carrousel.

Veille complète : https://djidonou.com/frontiere/

#economie #intelligenceartificielle #politiquespubliques #donnees

---

# Sources

- Manipulation-Robust Prediction. Daniel Björkegren, Joshua E. Blumenstock, Samsun Knight, American Economic Review, 2026-09-01. https://doi.org/10.1257/aer.20241087
- Pricing with Algorithms. Rohit Lamba, Sergey Zhuk, American Economic Review: Insights, 2026-09-01. https://doi.org/10.1257/aeri.20240436
- Macroeconomic Impacts of China's Energy Transition. Hugo Rojas-Romagosa, Gregor Schwerhoff, Sneha Thube, Sha Yu, IMF Working Papers, 2026-08-01. https://doi.org/10.5089/9798229060783.001

# A verifier avant publication

Les résumés du flux sont rédigés par un modèle de langage (gemini-3.6-flash, avec repli claude-haiku-4-5 sur cette exécution), pas par une lecture des articles. Confirme à la source tout chiffre, tout nom et tout énoncé de résultat avant de le publier sous ton nom.

Trois points précis à confirmer avant publication :

1. Le rapprochement avec la critique de Lucas en diapositive 3 est mon interprétation, pas une affirmation des auteurs.
2. « Expérience de terrain au Kenya » vient du résumé généré, la taille de l'échantillon n'est pas vérifiée.
3. L'énoncé « tous les équilibres de Markov parfaits sont supraconcurrentiels sur toute grille finie » reprend le résumé généré. La condition exacte mérite une lecture du théorème.
