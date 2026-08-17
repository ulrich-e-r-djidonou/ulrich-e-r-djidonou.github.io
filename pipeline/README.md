# Pipeline La Frontière

Trois étapes sont exécutées dans l'ordre par
`.github/workflows/frontiere.yml`, le lundi et le jeudi à 11 h UTC:

```powershell
python pipeline/collect.py
python pipeline/curate.py
python pipeline/publish.py
```

## Collecte et sélection

`collect.py` interroge les sources définies dans `sources.yaml` et écrit les
candidats bruts dans `pipeline/_candidats_bruts.json`. Un récapitulatif par
source (statut, nombre d'items) est aussi écrit dans
`pipeline/_collecte_sante.json`, ignoré par Git, pour diagnostiquer une
exécution à zéro publication sans rouvrir les journaux du workflow.

Quatre types de source : `arxiv` (flux natif), `rss` (VoxEU, Banque du
Canada, NBER, Fed, BCE), `crossref` (revues AEA par ISSN, FMI par ISSN, SSRN
par préfixe DOI) et `github_commits`.

Le flux RSS du NBER accole les auteurs au titre (`Titre -- by Auteur, Auteur`)
et ne porte aucune date : `separateur_auteurs` sépare les deux, `date_repli:
collecte` retient la date de collecte comme approximation, les items du flux
« new » étant par construction ceux de la semaine.

`collecter_rss` récupère le contenu avec `requests` avant de le passer à
`feedparser`, plutôt que de laisser `feedparser` interroger l'URL lui-même :
le magasin de certificats TLS qu'il utilise alors dépend de la plateforme, ce
qui faisait par exemple échouer le flux de la BCE en local tout en marchant
avec `requests`, qui embarque son propre magasin.

Crossref sert les revues AEA (AER, AER Insights, JEP, JEL, les quatre AEJ) et
la série IMF Working Papers par ISSN, datées par leur publication. Le préfixe
DOI du FMI (`10.5089`) mélange à lui seul rapports pays, notes techniques et
documents de politique : l'ISSN `1018-5941` isole la seule série de
recherche. SSRN est accessible par le préfixe DOI
`10.2139`, daté par son dépôt, seule date fiable puisque Crossref réduit
souvent la date de publication SSRN à l'année seule. SSRN reste désactivé par
défaut dans `sources.yaml` : Crossref ne porte aucune métadonnée de
discipline pour ce préfixe, si bien qu'il mélange économie, chimie et
médecine. Mesuré le 2 août 2026 : 2000 dépôts sur 7 jours, dont 214 passant
les deux filtres de mots-clés, un volume qui épuiserait `LLM_BUDGET_APPELS` au
détriment des autres sources.

Les mots-clés `MOTS_CLES_ECO` et `MOTS_CLES_IA` (dans `collect.py` et,
séparément, dans `curate.py` pour le score) sont des racines comparées par
sous-chaîne, volontairement : « econom » doit attraper « macroeconomics ».
Une exception : `llm`, seul acronyme de la liste qui apparaît aussi comme
sous-chaîne d'un mot anglais courant (« enrollment »), exige donc un début de
mot.

`curate.py` calcule un score déterministe, soit le nombre de mots-clés
économiques multiplié par le nombre de mots-clés IA ou ML. Le LLM ne
participe jamais au tri.

- score d'au moins 3: l'item est admissible à la sélection principale;
- score inférieur à 3: l'item rejoint l'archive avec ses métadonnées
  vérifiables, sans appel LLM.

Une exception tient au fait que certaines sources publient de l'économie par
construction: les revues de l'AEA, les working papers du NBER et du FMI, les
colonnes VoxEU/CEPR, la Banque du Canada, la Réserve fédérale américaine et
la Banque centrale européenne (`SOURCES_ECONOMIQUES` dans `curate.py`).
Pour celles-là, le compte de mots-clés économiques est planché au seuil, si
bien que l'article est jugé sur sa seule pertinence IA. Un comité scientifique
a déjà tranché la question que `MOTS_CLES_ECO` essaie de deviner, et le
vocabulaire d'un sous-champ n'a aucune raison de figurer dans une liste
généraliste.

Le cas qui a motivé cette règle, le 5 août 2026: « The Emerging Market for
Intelligence: How Firms Buy and Sell AI » (JEP, DOI 10.1257/jep.20261506),
archivé avec un score de 2 parce que son résumé parle de prix, de fournisseurs
et de différenciation, sans employer les mots généralistes de la liste. Un
article du *Journal of Economic Perspectives* échouait donc au test « est-ce de
l'économie ». Les deux corrections évidentes ont été mesurées puis écartées sur
127 articles réels: abaisser le seuil à 2 faisait entrer 35 articles de plus,
dont des papiers d'ingénierie informatique sans contenu économique; enrichir la
liste de mots en faisait entrer 18, avec le même défaut atténué. La règle par
source en rattrape 5, tous pertinents, sans aucun faux positif.

Les fichiers intermédiaires sont ignorés par Git:

- `pipeline/_candidats_cures.json`;
- `pipeline/_candidats_archives.json`.

## Rédaction

Les items admissibles sont rédigés en français par un modèle. Deux
fournisseurs, choisis par `FRONTIERE_LLM`. Le fournisseur ne change que la
rédaction, jamais la sélection, qui reste heuristique.

La production utilise `gemini-3.6-flash` par le palier gratuit de l'API
Gemini. Ce palier accorde 20 requêtes par jour et par modèle, ce qui suffit à
deux exécutions hebdomadaires. `LLM_BUDGET_APPELS` arrête la rédaction avant
d'atteindre la limite: les items non rédigés ne sont pas marqués vus et
reviennent à l'exécution suivante, comme après une panne. Aucun paiement n'est
nécessaire, l'achat de crédits Google exigeant un minimum de 20 CAD non
remboursables pour une consommation réelle inférieure à 1 CAD par an.

Modèle local, l'option de repli:

```text
FRONTIERE_LLM=ollama
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_URL=http://localhost:11434/api/generate
```

Service distant au format OpenAI, DeepSeek, Gemini ou équivalent:

```text
FRONTIERE_LLM=api
LLM_API_URL=https://api.deepseek.com/v1/chat/completions
LLM_API_MODELE=deepseek-v4-flash
LLM_API_CLE=...
```

Un second point de terminaison de repli, au même format, peut être ajouté à
côté. `curate.py` n'y recourt que si le fournisseur principal échoue après ses
propres tentatives (quota épuisé, panne) ; la bascule vaut ensuite pour le
reste de l'exécution. `LLM_BUDGET_APPELS` reste un seul compteur, tous
fournisseurs confondus.

```text
LLM_API_URL_REPLI=https://api.anthropic.com/v1/chat/completions
LLM_API_MODELE_REPLI=claude-haiku-4-5
LLM_API_CLE_REPLI=...
```

En `.github/workflows/frontiere.yml`, ce repli est configuré vers Claude
(`claude-haiku-4-5`, via l'endpoint compatible OpenAI d'Anthropic), pour le
cas où le palier gratuit de Gemini est épuisé avant la fin du lot, comme le 3
août 2026.

En production la clé passe par un secret GitHub, jamais par le dépôt. Le repli
en a un second, distinct de celui du fournisseur principal:

```powershell
gh secret set LLM_API_CLE
gh secret set LLM_API_CLE_REPLI
```

Volume mesuré sur le banc: 942 jetons en entrée et 218 en sortie par item,
soit environ 245 000 et 57 000 jetons par an à 5 items par semaine. Aux
tarifs d'août 2026, cela place le coût annuel entre 0,05 et 0,87 USD selon le
modèle retenu.

Le résumé et l'angle économique possèdent des validateurs distincts. Chaque
champ peut être généré deux fois au maximum. Aucun extrait anglais n'est
utilisé comme repli.

Deux échecs sont distingués, parce qu'ils n'appellent pas la même réaction:

- **échec de validation**: le modèle a répondu, mal. L'item n'est pas publié
  et reste marqué dans `pipeline/seen.json`. Il ne sera pas repêché.
- **service indisponible**: le modèle n'a pas répondu, après une reprise.
  `curate.py` s'arrête sans rien écrire, donc sans marquer aucun item, et
  sort en code 1. Le workflow échoue visiblement plutôt qu'une panne ne
  consomme définitivement un lot d'articles.

Les contrôles portent sur trois plans.

**Forme**: nombre de phrases, ponctuation finale, caractères non latins, fuite
de mots outils anglais.

**Langue**: élision manquante, démonstratif devant voyelle, mot doublé, fuite
de mot anglais isolé, et le faux ami `trillion`, qui vaut 10^12 en anglais
contre 10^18 en français.

**Posture éditoriale**: aucune ouverture qui parle du papier plutôt que de son
contenu, aucune première personne, puisque le flux résume les travaux des
autres, et aucun renvoi du type « ces difficultés » à un antécédent que le
lecteur n'a pas sous les yeux, chaque champ étant lu seul.

Ces règles sont volontairement étroites et ne couvrent ni les accords en genre
ni le style. Passées sur la prose française du site, elles ne produisent aucun
faux positif.

La calibration sur les sorties existantes se lance avec:

```powershell
python -m pipeline.calibrer_validateurs --git-ref 3f406d40d7b9bc8ad7d58895d6984cc2ec33fe51
python -m pipeline.calibrer_validateurs frontiere/data/flux.json
```

## Publication

`publish.py` conserve dans `frontiere/data/flux.json` les items récents dont
le score atteint 3. Les items sous le seuil ou sortis de la fenêtre de 90
jours sont écrits dans `frontiere/data/archives/AAAA-MM.json`.

Le script met aussi à jour:

- `frontiere/data/meta.json`;
- `frontiere/feed.xml`;
- le champ `lastmod` de `/frontiere/` dans `sitemap.xml`.

Le workflow indexe explicitement `sitemap.xml` avec les sorties du pipeline.

### Signal de la semaine

`designer_signal` marque d'un drapeau `signal` l'entrée mise en avant en tête
de la page. Le choix se fait par paliers de fraîcheur décroissante, le premier
non vide gagnant: les items rapportés par l'exécution en cours, sinon ceux
publiés depuis 7 jours, sinon la fenêtre entière. Le dernier palier n'est
atteint que par une exécution sans récolte, cas où reproposer le meilleur du
trimestre vaut mieux que vider la section.

Les paliers ne couvrent qu'une exécution vide, jamais un score faible. Le
signal se choisissait auparavant sur les 90 jours sans contrainte de
fraîcheur, si bien que le mieux noté gardait la place jusqu'à sortir de la
fenêtre: constaté le 17 août 2026, un article du 10 août la tenait depuis une
semaine et l'aurait tenue deux mois de plus. Laisser un score faible
redescendre d'un palier reproduirait ce défaut.

`SEUIL_SIGNAL` vaut 6, le double du seuil de publication. Le score étant le
produit du nombre de mots-clés économiques par celui des mots-clés IA, 6 exige
les deux dimensions franchement présentes, 2 x 3 au moins. Sous ce plancher
aucun signal n'est désigné et la page indique qu'aucun article ne ressort du
lot, plutôt que d'en mettre un en avant sans le mériter. La carte de l'accueil
laisse alors sa ligne de teaser masquée.

## Rédaction à nouveau des items déjà publiés

Un correctif de prompt ou de validateur ne nettoie que les items à venir.
`regenerer_flux.py` rejoue la rédaction des items déjà en ligne à partir du
corpus figé du banc, sans réinterroger les API sources et sans toucher à
`pipeline/seen.json`. Le modèle utilisé est celui de la production.

```powershell
$env:FRONTIERE_LLM = "ollama"
python -m pipeline.regenerer_flux              # relecture seule
python -m pipeline.regenerer_flux --appliquer  # après relecture
```

Sans `--appliquer`, rien n'est écrit dans `frontiere/data/`. Le script produit
`pipeline/_regeneration.json`, un avant/après par item avec le détail des
essais. Les items rejetés par la validation gardent leur texte précédent.

`--depuis-relecture` applique le contenu de `pipeline/_regeneration.json` sans
rien régénérer, pour garantir que le texte publié est exactement celui qui a
été relu : le modèle ne produit pas deux fois la même sortie.

Le workflow manuel `regenerer-flux` (`.github/workflows/regenerer-flux.yml`,
`workflow_dispatch`) rejoue cette même reprise côté GitHub Actions, avec le
secret `LLM_API_CLE` déjà en place là-bas, donc sans clé à gérer en local.
Un déclenchement sans l'option « appliquer » relit les items restants et
publie l'avant/après dans le résumé de l'exécution ; un second déclenchement,
avec l'option activée, applique cette relecture avec `--depuis-relecture`,
sans repasser par le modèle. L'état intermédiaire (`_regeneration.json` et
`.md`, tous deux ignorés par Git) passe d'une exécution à l'autre par le cache
d'Actions, chaque sauvegarde utilisant une clé unique puisque le cache est
immuable pour une clé donnée.

## Tests

```powershell
python -m unittest pipeline.test_curate pipeline.test_publish pipeline.test_collect pipeline.test_verifier_sante pipeline.test_verifier_jsonld pipeline.benchmark.test_benchmark -v
python -m py_compile pipeline/curate.py pipeline/publish.py
```

`.github/workflows/tests.yml` exécute ces tests à chaque poussée touchant
`pipeline/`, puis rejoue la calibration des validateurs sur le flux publié.
La calibration sort en code 2 si le taux de rejet hors formule dépasse 20 %,
seuil au-delà duquel la non-publication ferait chuter le volume du flux.

## Validation du balisage schema.org

`verifier_jsonld.py` relit `index.html` et `frontiere/index.html`, extrait
chaque bloc `application/ld+json` et vérifie qu'il est du JSON bien formé et
que les champs attendus pour son `@type` sont présents et non vides
(`Person`, `WebSite`, `WebPage`, `FAQPage`, `CollectionPage`, `ItemList`, et
chaque `CreativeWork` imbriqué dans un `ItemList`). Pour un `CreativeWork`, il
vérifie en plus que `citation.url` et `citation.author` sont renseignés : sans
cette distinction, un lecteur automatisé attribuerait le travail cité à
l'auteur du site plutôt qu'à ses propres auteurs.

Ne contrôle que la structure, pas l'exactitude du contenu ni ce que Google
affiche réellement : il n'existe pas d'équivalent scriptable du Rich Results
Test sans passer par l'API Search Console, qui exige une authentification
OAuth hors de portée d'un script CI simple.

Dans `frontiere.yml`, ce contrôle se lance après `publish.py` mais avant le
commit, à la différence de `verifier_sante.py` : un JSON-LD cassé est une
régression réelle, pas un signal à surveiller, et ne doit jamais être publié.

```powershell
python -m pipeline.verifier_jsonld
```

## Alerte de santé

`curate.py` journalise chaque exécution (items éligibles, publiés, reportés,
rejetés par la validation, fournisseur) dans `frontiere/data/sante.json`,
committé, sur les 12 dernières exécutions.

`publish.py` complète ensuite la ligne du jour avec `signal_designe` et
`score_max`, le meilleur score de la récolte. Il la complète sur place au lieu
d'en écrire une seconde: `curate.py` tourne avant lui, donc avant que le signal
soit désigné, et deux lignes à la même date feraient compter deux exécutions là
où il n'y en a eu qu'une. Si la ligne du jour manque, parce que `publish.py` a
été lancé seul hors du workflow, rien n'est créé plutôt qu'une ligne à moitié
vide.

`verifier_sante.py` se lance après la publication, dans le workflow, et
échoue si les deux dernières exécutions ont publié zéro item. Il ne bloque
jamais la maintenance du flux : dans `frontiere.yml`, il se lance après le
commit, pas avant. Une seule exécution à zéro peut être une semaine creuse ;
deux d'affilée signalent plus probablement une source toutes en échec, un
filtre de mots-clés devenu trop strict, ou un budget d'appels
systématiquement épuisé avant la fin du lot. Un échec fait échouer le
workflow visiblement, comme pour une panne du service de rédaction, ce qui
déclenche la notification GitHub par défaut sur les exécutions planifiées.

Le même script rapporte l'issue du signal, et celui-ci demandait sa propre
surveillance depuis que le plancher a rendu la section vide possible: une
exécution peut publier ses neuf items, ne désigner aucun signal, et paraître en
parfaite santé, `nb_publies` étant le seul chiffre surveillé. Une quinzaine
calme et un scoring qui a cessé de fonctionner produisent alors le même écran.
Quatre exécutions consécutives sans signal, environ deux semaines, déclenchent
un rapport listant les `score_max` de la période.

Ce rapport est informatif, là où l'alerte à zéro publication est bloquante, et
l'écart se justifie par le taux de fausse alerte. Zéro item publié deux fois de
suite est presque toujours une panne. Une quinzaine sans article marquant reste
plausible sur un flux de veille, et faire échouer le workflow dessus
apprendrait à ignorer ses échecs, ce qui coûte plus cher que de rater
l'information.

`score_max` est journalisé à chaque exécution, y compris quand tout va bien.
`SEUIL_SIGNAL` a été fixé le 17 août 2026 sur une seule semaine de données et
un raisonnement sur la structure du score, jamais sur une distribution
observée: ces lignes sont la matière qui permettra de le réviser. Des maximums
qui s'écrasent sous le plancher exécution après exécution désignent le scoring,
donc les listes de mots-clés ou la forme des résumés servis par les sources.
Des maximums qui frôlent le plancher sans l'atteindre désignent le plancher
lui-même.

Les lignes antérieures au 17 août 2026 ne portent pas `signal_designe` et sont
ignorées par ce contrôle, plutôt que comptées comme des absences de signal, ce
qui déclencherait l'alerte sur du passé qui n'en savait rien.

```powershell
python -m pipeline.verifier_sante
```

## Comparaison des modèles

Le dossier [`pipeline/benchmark`](benchmark/README.md) contient le corpus
figé de 61 items, l'exécuteur Ollama, les résultats automatiques et le
protocole d'évaluation humaine à l'aveugle. Le banc ne modifie pas le modèle
de production.
