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

En production la clé passe par un secret GitHub, jamais par le dépôt:

```powershell
gh secret set LLM_API_CLE
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
