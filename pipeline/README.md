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
candidats bruts dans `pipeline/_candidats_bruts.json`.

`curate.py` calcule un score déterministe, soit le nombre de mots-clés
économiques multiplié par le nombre de mots-clés IA ou ML. Le LLM ne
participe jamais au tri.

- score d'au moins 3: l'item est admissible à la sélection principale;
- score inférieur à 3: l'item rejoint l'archive avec ses métadonnées
  vérifiables, sans appel LLM.

Les fichiers intermédiaires sont ignorés par Git:

- `pipeline/_candidats_cures.json`;
- `pipeline/_candidats_archives.json`.

## Rédaction locale avec Ollama

Les items admissibles sont rédigés en français par Ollama. Le workflow de
production utilise actuellement `qwen2.5:3b`.

```text
FRONTIERE_LLM=ollama
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_URL=http://localhost:11434/api/generate
```

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

Les contrôles portent sur le nombre de phrases, les caractères non latins, la
fuite de mots outils anglais, les ouvertures stéréotypées et un jeu de règles
de langue française: élision manquante, démonstratif devant voyelle, mot
doublé, fuite de mot anglais isolé, et le faux ami `trillion`, qui vaut 10^12
en anglais contre 10^18 en français. Ces règles sont volontairement étroites
et ne couvrent ni les accords en genre ni le style.

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

## Tests

```powershell
python -m unittest pipeline.test_curate pipeline.test_publish pipeline.benchmark.test_benchmark -v
python -m py_compile pipeline/curate.py pipeline/publish.py
```

`.github/workflows/tests.yml` exécute ces tests à chaque poussée touchant
`pipeline/`, puis rejoue la calibration des validateurs sur le flux publié.
La calibration sort en code 2 si le taux de rejet hors formule dépasse 20 %,
seuil au-delà duquel la non-publication ferait chuter le volume du flux.

## Comparaison des modèles

Le dossier [`pipeline/benchmark`](benchmark/README.md) contient le corpus
figé de 61 items, l'exécuteur Ollama, les résultats automatiques et le
protocole d'évaluation humaine à l'aveugle. Le banc ne modifie pas le modèle
de production.
