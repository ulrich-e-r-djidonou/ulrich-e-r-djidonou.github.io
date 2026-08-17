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

## 2026-08-17, empêcher un lancement nu de détruire le signal

Réponse aux deux fausses manoeuvres relevées dans l'entrée ci-dessous. Elles
avaient la même cause: `publish.py` s'exécute volontiers hors de son contexte et
écrit dans les fichiers publiés sans rien demander. Lancé sans
`_candidats_cures.json`, il voyait une récolte vide et redésignait le signal sur
un vivier inexistant, ce qui détruisait celui en place.

La distinction qui manquait: l'absence de récolte n'est pas une récolte vide.
Le fichier de candidats absent signifie que ce n'est pas une publication, pas
qu'il n'y avait rien à publier. `publish.py` conserve donc le signal tel quel
dans ce cas, en le disant clairement.

Le garde-fou ne gèle pas le reste. La fenêtre, les archives, le flux RSS et le
sitemap continuent d'être tenus, parce que c'est précisément ce qu'on veut
pouvoir relancer à la main. Deux tests couvrent les deux moitiés: le signal
préservé, et la maintenance qui se poursuit.

Un échec dur aurait été plus simple à écrire, mais il aurait interdit la
maintenance manuelle, qui est un usage légitime. Protéger la seule chose
fragile vaut mieux que bloquer l'outil entier.

## 2026-08-17, un outil pour calibrer le plancher plutôt qu'une promesse

`relever_scores_signal.py` lit les `score_max` du carnet et dit ce qu'un autre
plancher aurait donné. Écrit maintenant, alors que le carnet ne contient que
deux mesures, parce qu'un outil disponible se consulte, là où un rapport promis
pour dans un mois se serait perdu.

Trois choix de conception valent d'être retenus, tous du même ordre: refuser de
conclure plus loin que ce que les données permettent.

Le script ne recommande rien sous huit exécutions mesurées, environ un mois.
Quatre exécutions couvrent deux semaines, et deux semaines calmes ne sont pas
une tendance. Il décrit alors, sans conclure.

Il distingue un plancher qui convient d'une distribution où aucun plancher ne
convient. C'est un test qui a révélé le défaut: la première version répondait
« rien à changer » dans les deux cas, y compris quand le plancher ne désignait
un signal que 10 % du temps. La formulation faisait lire « tout va bien » là où
la vraie conclusion est que les scores sont trop concentrés pour qu'un seuil les
sépare, ce qui met en cause le score lui-même et non le seuil.

À couverture acceptable égale, il retient le plancher le plus élevé plutôt que
le plus central, parce qu'un plancher haut sélectionne mieux à qualité de
couverture identique.

La fourchette visée, 40 à 85 % d'exécutions avec signal, reste un jugement, pas
une mesure. Elle est écrite dans le code avec son motif, pour être discutée
plutôt que subie.

---

## 2026-08-17, le vivier du signal est la semaine, pas l'exécution

Défaut trouvé en lançant le workflow à la main pour vérifier les trois entrées
ci-dessous. L'exécution manuelle, onze heures après celle du matin, n'a
rapporté que deux items faibles, et la page est passée d'un signal valide à
« aucun article ne ressort du lot » alors que trois articles à 6 dormaient dans
les sept derniers jours.

La cause est une décision prise plus tôt dans la journée, et elle était trop
étroite: le vivier se limitait aux items de l'exécution en cours, les paliers
de repli ne couvrant qu'une récolte vide, jamais un score faible. Le
raisonnement se défendait pour empêcher le repli de ressusciter l'article du 10
août, mais il rendait le signal otage de la dernière récolte. Deux exécutions
le même jour, ou un jeudi calme, et la semaine perd son signal. Une récolte
maigre n'est pas une semaine vide.

Le vivier est donc devenu la semaine: les items de l'exécution réunis à ceux
publiés depuis sept jours. Ce qui rouvrait la question d'origine, puisque
l'article du 10 août était encore dans les sept jours le 17, donc encore
éligible. Une fenêtre glissante seule ne produit pas de rotation.

D'où `deja_signal`, marqueur définitif: un article a son tour en tête de page,
une fois. C'est lui, et non la fraîcheur, qui garantit ce qu'Ulrich demandait
au départ, ne plus revoir le même article d'une semaine sur l'autre. Il est
reporté quand une entrée déjà publiée est rédigée à nouveau, sinon
`regenerer_flux.py` ferait revenir un article déjà vu.

Le rattrapage des articles passés a été reconstitué depuis l'historique Git de
`flux.json`, vingt-cinq versions parcourues, plutôt que de mémoire: six
articles ont porté le drapeau à un moment. Les six sont marqués. Deux d'entre
eux n'ont été affichés que quelques minutes, pendant les itérations de la
journée, et on aurait pu les épargner en jugeant que leur exposition ne
comptait pas. Ce critère aurait été invérifiable et laissé à mon appréciation,
là où le registre publié tranche seul. Le signal du jour devient *AI Financial
Advice: Supply, Demand, and Life Cycle Implications*, score 6.

Deux fausses manoeuvres de ma part dans la même séquence, notées parce qu'elles
disent quelque chose du montage. Lancer `publish.py` en local, pour tester un
import, a réécrit `flux.json` avec un run vide et fait remonter l'ancien
article; les fichiers ont été restaurés depuis HEAD après vérification. Puis
une redésignation manuelle a écrasé `score_max` avec une récolte vide passée en
argument, chiffre rétabli depuis le journal du workflow. Les deux viennent de
la même cause: le pipeline s'exécute volontiers hors de son contexte et écrit
dans les fichiers publiés sans rien demander.

C'est aussi ce qui a motivé, dans la foulée, de résoudre les chemins de
`synchroniser_sitemap` et `injecter_jsonld_flux` à l'appel plutôt que dans leur
signature. Liés par défaut à l'import, ils désignaient les vrais fichiers du
site, et le test de bout en bout de `main()` aurait réécrit `sitemap.xml` et
`frontiere/index.html` au lieu de son bac à sable.

---

## 2026-08-17, à score égal, le poids économique départage

Décision d'Ulrich, prise en connaissance des deux entrées ci-dessous: garder
l'article au score maximal comme signal, l'essayer tel quel, et ajuster si la
qualité ne suit pas. Avec une préférence explicite pour trancher les égalités,
qui est le vrai apport ici. À score égal, l'article le plus économique passe
devant; à poids égal, celui dont le titre porte le vocabulaire économique.

Le motif tient à la forme du score, qui est un produit et non une somme. Un 6
vaut 2 x 3 ou 3 x 2, et le score seul ne distingue pas un article très
économique modérément IA d'un article très IA modérément économique. Pour une
veille tenue par un économiste, ces deux articles n'ont pas le même intérêt,
et le classement précédent les départageait par leur date, c'est-à-dire par un
critère sans rapport avec ce qui est cherché.

L'ordre est donc: score, `nb_eco`, mots-clés économiques du titre, date. La
date ne disparaît pas, elle descend en dernier, où elle garantit un ordre
total. Sans elle, deux entrées strictement équivalentes se classeraient selon
leur position dans le fichier, donc selon l'ordre de collecte, ce qui est
arbitraire sans être stable.

Effet immédiat, et il valide la règle. Les deux articles à 6 du 17 août étaient
départagés par la date, ce qui donnait *Making AI Tutoring Productive*. Le
titre économique fait passer devant *Macrofinance meets AI: Evaluating
alignment between LLMs and economists*, nettement plus proche de la veille
qu'Ulrich tient.

Une contrainte de données a orienté la mise en oeuvre. Le score se calcule sur
le titre plus l'abstract anglais, or l'abstract n'est pas versé dans le flux:
`publish.py` ne pouvait donc pas recalculer les comptes après coup. `curate.py`
les conserve désormais dans chaque entrée, `compter_mots_cles` ayant été
extrait de `score_heuristique` pour les exposer avant leur multiplication. Les
entrées antérieures ne les portent pas et ne sont départagées que sur leur
titre, ce qui reste exact faute d'être complet. Comme le signal se choisit
d'abord parmi la récolte du jour, dont toutes les entrées porteront les champs,
cette approximation ne concerne que les paliers de repli.

`poids_economique_titre` importe `MOTS_CLES_ECO` depuis `curate.py` plutôt que
d'en tenir une copie: deux listes qui dérivent l'une de l'autre feraient
départager le signal sur un vocabulaire différent de celui qui l'a rendu
éligible, et rien ne signalerait la divergence.

Cet import a révélé un piège d'exécution qui ne se serait vu qu'en production.
Le workflow lance `python pipeline/publish.py`, ce qui met `pipeline/` sur le
chemin d'import, alors que les tests font `from pipeline import publish`, ce
qui y met la racine du dépôt. Une seule des deux formes d'import casse l'autre,
et la version qui passe les tests est justement celle qui échouerait le lundi
suivant, en silence, dans une exécution planifiée. Les deux sont donc
supportées.

---

## 2026-08-17, surveiller l'absence de signal et mesurer les scores

Suite immédiate de l'entrée ci-dessous, dont le correctif a ouvert un trou de
surveillance en même temps qu'il réparait la règle.

Avant le plancher, la section Signal ne pouvait pas être vide: il existait
toujours un article au score maximal, même médiocre. Depuis, elle peut l'être,
et deux causes très différentes produisent le même écran. Une quinzaine calme,
ce qui est légitime. Ou un scoring qui a cessé de fonctionner, parce qu'une
source a changé la forme de ses résumés ou qu'un filtre est devenu trop strict,
auquel cas tous les scores s'écrasent entre 3 et 4 et la section reste vide
indéfiniment.

Ce second cas était invisible. La surveillance ne regardait que `nb_publies`,
et l'exécution du 17 août montre bien le problème: 9 items publiés, aucune
bascule de repli, aucun rejet, `verifier_sante.py` répond « ok ». Le pipeline
est en parfaite santé du point de vue de ce qu'il mesure. Seul le signal
disparaîtrait, et rien ne mesurait le signal. C'est la classe de panne
silencieuse que `verifier_fraicheur_sources.py` traque déjà au niveau des
sources, où un flux qui répond 200 avec un XML valide et zéro entrée récente ne
lève aucune erreur.

Deux champs ajoutés au carnet, `signal_designe` et `score_max`. Le second est
le plus utile, et pour une raison qui touche à l'entrée précédente: le plancher
de 6 a été fixé sur une seule semaine de données et un raisonnement sur la
structure du score. C'est un jugement, pas une mesure. Journaliser le meilleur
score de chaque récolte donne la distribution réelle, donc la possibilité de
réviser le plancher sur des chiffres. Le rapport dit d'ailleurs comment lire
ces chiffres: des maximums écrasés sous le plancher accusent le scoring, des
maximums qui le frôlent accusent le plancher.

Deux arbitrages méritent d'être retenus.

Le rapport est informatif, non bloquant, contrairement à l'alerte à zéro
publication. Rendre bloquant un contrôle dont la fausse alerte est plausible,
et une quinzaine sans article marquant l'est sur un flux de veille, apprend à
ignorer les échecs du workflow. Ce coût dépasse celui de rater l'information,
puisqu'il dégrade aussi les alertes qui, elles, sont fiables.

Les lignes antérieures à cette date sont ignorées faute de porter le champ,
au lieu d'être comptées comme des absences de signal. Sans cette précaution
l'alerte se serait déclenchée dès la première exécution sans signal, en
additionnant trois exécutions passées qui n'en savaient rien, exactement le
genre de test qui se déclenche tout seul et que
`pipeline/verifier_dates_tests.py` existe pour prévenir ailleurs.

La ligne du 17 août a été complétée à la main, via la fonction elle-même,
plutôt qu'attendre l'exécution du jeudi: le carnet ne garde que 12 exécutions,
et la seule dont on connaissait déjà l'issue en détail méritait d'y figurer.

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
