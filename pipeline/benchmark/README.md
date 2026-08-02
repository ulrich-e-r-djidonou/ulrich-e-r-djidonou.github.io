# Banc de comparaison des modèles

Ce dossier compare des modèles Ollama pour la rédaction de La Frontière. Il
ne modifie ni `OLLAMA_MODEL` ni le workflow de production.

## Corpus

Le corpus figé contient les 61 items présents dans
`frontiere/data/flux.json` au commit
`3f406d40d7b9bc8ad7d58895d6984cc2ec33fe51`.

- 57 abstracts proviennent de l'API arXiv.
- 2 résumés VoxEU proviennent du RSS public de CEPR.
- Le papier sur le conseil financier est récupéré par Crossref, DOI
  `10.2139/ssrn.6446286`.
- Le papier sur la productivité est récupéré par OpenAlex à partir de la
  version NBER, DOI `10.3386/w34984`.

Le fichier `corpus.json` est versionné et porte une empreinte SHA-256. Le
reconstruire avec les sources courantes peut produire une autre empreinte si
une source a été révisée. Le fichier versionné reste l'autorité du benchmark
réalisé le 2 août 2026.

Commande de reconstruction:

```powershell
python -m pipeline.benchmark.reconstruire_corpus
```

## Modèles

Le banc compare:

- `qwen2.5:3b`, modèle de production au moment du test;
- `qwen2.5:7b`;
- `llama3.2:3b`, troisième modèle de taille comparable déjà présent dans
  l'environnement local.

Installation locale:

```powershell
ollama pull qwen2.5:3b
ollama pull qwen2.5:7b
ollama pull llama3.2:3b
```

## Exécution

Le script utilise les prompts et validateurs de `pipeline/curate.py`. La
température est fixée à 0 et la graine à 20260802. Chaque champ peut être
généré deux fois au maximum, conformément à la politique de production.

```powershell
python -m pipeline.benchmark.comparer_modeles
```

`resultats.json` est sauvegardé après chaque couple item-modèle. Relancer la
même commande reprend les résultats déjà présents si l'empreinte du corpus
est identique.

## Rapport et évaluation humaine

```powershell
python -m pipeline.benchmark.generer_rapport
```

Cette commande produit:

- `rapport_comparatif.md`, métriques automatiques et temps d'exécution;
- `evaluation_aveugle.csv`, 10 items et trois options anonymisées;
- `cle_evaluation_aveugle.json`, correspondance séparée entre options et
  modèles.

Le coût API direct est nul parce que l'exécution est locale. Le coût
énergétique et le coût matériel ne sont pas mesurés. Les métriques
automatiques ne suffisent pas à choisir un modèle. La décision finale revient
à l'auteur du site après lecture de l'échantillon aveugle.
