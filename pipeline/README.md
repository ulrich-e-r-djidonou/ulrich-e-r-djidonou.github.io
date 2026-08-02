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
champ peut être généré deux fois au maximum. Si la seconde sortie échoue,
l'item n'est pas publié et reste marqué dans `pipeline/seen.json`. Aucun
extrait anglais n'est utilisé comme repli.

Les contrôles portent notamment sur le nombre de phrases, les caractères non
latins, la fuite de mots outils anglais et les ouvertures stéréotypées. La
calibration sur les sorties existantes se lance avec:

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

## Tests

```powershell
python -m unittest pipeline.test_curate pipeline.test_publish -v
python -m py_compile pipeline/curate.py pipeline/publish.py
```

## Comparaison des modèles

Le dossier [`pipeline/benchmark`](benchmark/README.md) contient le corpus
figé de 61 items, l'exécuteur Ollama, les résultats automatiques et le
protocole d'évaluation humaine à l'aveugle. Le banc ne modifie pas le modèle
de production.
