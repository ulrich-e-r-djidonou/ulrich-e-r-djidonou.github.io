# Pipeline La Frontiere

Trois etapes, executees dans l'ordre par `.github/workflows/frontiere.yml`
(cron lundi et jeudi 11h UTC, ou `workflow_dispatch` manuel) :

```
python pipeline/collect.py   # collecte multi-sources (sources.yaml)
python pipeline/curate.py    # scoring heuristique + resume (mode degrade ou Ollama)
python pipeline/publish.py   # fusion, fenetre 90 jours, archives, feed.xml
```

## Mode par defaut : heuristique, sans dependance externe

Sans configuration supplementaire, `curate.py` calcule un score deterministe
(nombre de mots-cles economie x nombre de mots-cles IA/ML) et un resume qui
est un simple extrait de l'abstract original, prefixe
`[Extrait original, traduction non disponible]` quand la source est en
anglais. Aucun appel reseau, aucune cle API requise.

## Mode optionnel : Ollama pour la redaction (pas pour le tri)

Le scoring reste **toujours** heuristique, meme quand Ollama est actif : un
LLM ne sert jamais a decider quels items publier, seulement a rediger, pour
les items deja retenus par le seuil, un resume en francais et une ligne
"pourquoi ca compte pour un economiste" (`angle_eco`).

Pour activer, definir ces variables d'environnement avant d'executer
`curate.py` :

```
FRONTIERE_LLM=ollama
OLLAMA_MODEL=qwen2.5:3b       # optionnel, defaut qwen2.5:3b
OLLAMA_URL=http://localhost:11434/api/generate   # optionnel
```

Dans GitHub Actions, le workflow installe et demarre Ollama dans le runner
avant d'executer le pipeline (voir `.github/workflows/frontiere.yml`) :
aucun secret requis, le modele tourne localement dans le job.

### En local, avec un modele plus gros

Si un Ollama local est deja installe avec un modele plus capable, executer
directement :

```
FRONTIERE_LLM=ollama OLLAMA_MODEL=qwen2.5:14b python pipeline/curate.py
```

### Garanties de secours (le run ne casse jamais)

- Chaque appel Ollama a un timeout de 60 secondes.
- Toute erreur (Ollama absent, timeout, reponse vide ou invalide) retombe
  silencieusement sur `resume_heuristique()` pour cet item precis : le reste
  du run continue normalement.
- Les items rediges par Ollama portent un champ `"llm": "<nom-du-modele>"`
  dans le JSON produit, absent pour les items en mode heuristique. Le front
  (`frontiere.js`) affiche une mention discrete "Résumé assisté par IA
  locale" uniquement sur ces items.
- Debrancher `FRONTIERE_LLM` redonne exactement le comportement heuristique
  d'origine, sans aucune autre modification.
