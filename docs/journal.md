# Journal de bord du site

Ce journal retient les décisions dont le motif ne se lit pas dans le code:
pourquoi une règle a été changée, quel incident l'a déclenchée, ce qui a été
écarté. Ce que le code dit déjà de lui-même n'y figure pas.

Il commence le 17 août 2026. Les décisions antérieures vivent dans
l'historique Git, dans les commentaires du code et dans
[`pipeline/README.md`](../pipeline/README.md), qui documente la méthode du
pipeline de La Frontière. Ce journal ne les récrit pas après coup: une
reconstitution de mémoire donnerait l'assurance d'une source d'archive à des
souvenirs approximatifs.

Convention: une entrée par décision, la plus récente en tête, datée en
absolu, avec le motif et le numéro de PR quand il en existe une.

---

## 2026-08-17, le signal de la semaine se choisit sur la collecte du jour

PR [#18](https://github.com/ulrich-e-r-djidonou/ulrich-e-r-djidonou.github.io/pull/18).

Ulrich a remarqué que le signal mis en avant sur `/frontiere/` était le même
que la semaine précédente. Vérification faite, ce n'était pas une panne du
workflow, qui avait bien tourné ce matin-là, mais la règle de sélection
elle-même: `publish.py` prenait le mieux noté de la fenêtre de 90 jours, sans
aucune contrainte de fraîcheur. *AI Agents and Prompt Engineering in
Econometric Coding*, score 9 publié le 10 août, occupait donc la place depuis
une semaine et l'aurait tenue jusqu'à sortir de la fenêtre, soit deux mois de
plus, faute d'un article mieux noté. La distribution rendait l'attente longue:
un seul 9 et deux 8 sur 56 entrées. Le libellé annonçait une semaine et
décrivait un classement trimestriel.

Le choix se fait maintenant par paliers de fraîcheur décroissante, les items
de l'exécution en cours d'abord. Le détail de la règle est dans
[`pipeline/README.md`](../pipeline/README.md); ce qui mérite d'être retenu
ici, c'est ce qui a été écarté. Faire redescendre d'un palier un candidat sous
le plancher paraissait naturel et aurait été le bon réflexe pour un mécanisme
de repli ordinaire. C'était le piège: le palier suivant contient l'article à
9, donc le repli aurait ressuscité l'ancien signal, c'est-à-dire exactement le
défaut corrigé. Les paliers ne couvrent qu'une exécution sans récolte, jamais
un score faible.

Le plancher a été fixé à 6 plutôt qu'à 7, ce qui aurait fait apparaître le
message dès cette semaine-là. Avec 27 entrées à 3 et 16 à 4, un plancher à 7
aurait laissé la section vide la plupart des semaines, et un message
d'exception affiché en permanence cesse d'être lu comme une exception.

Effet immédiat: les 9 items rapportés le 17 août plafonnaient à 6, atteint par
deux d'entre eux. Le signal est devenu *Making AI Tutoring Productive*, publié
le jour même. `flux.json` a été redésigné selon la nouvelle règle sans
attendre l'exécution du jeudi, pour ne pas laisser la page fausse trois jours
de plus.

Deux effets de bord corrigés au passage, tous deux invisibles avant que le
plancher rende l'absence de signal possible. La carte de l'accueil se rabattait
sur `entrees[0]`, donc aurait présenté le dernier article collecté comme
« dernier signal », une mise en avant que la sélection lui refuse. Et
`rendreSignal` lisait l'état du jeu affiché, archives comprises: le message du
plancher se serait affiché en consultant une archive, qui par construction n'a
jamais de signal.
