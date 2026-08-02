# Comparaison des modèles de La Frontière

## Objet

Ce banc compare trois modèles locaux sur le même corpus figé de 61 articles. Il mesure la conformité automatique et le temps d'exécution. Il ne change pas le modèle utilisé en production.

## Corpus et protocole

- Commit source : `3f406d40d7b9bc8ad7d58895d6984cc2ec33fe51`
- Empreinte du corpus : `1fe3093e4ae2b8de6d60be432785ce7dfbd7bdb661e8c5e62b0f28a04ffd8428`
- Nombre d'items : 61
- Température : 0
- Graine : 20260802
- Deux essais au maximum par résumé et par angle
- Coût API direct : 0 CAD, exécution locale
- Coût énergétique et coût matériel : non mesurés

## Résultats automatiques

Les taux par validateur portent sur le premier essai. La non-publication porte sur l'état final après une reprise au maximum.

| Modèle | Items | Résumé, phrases | Non latin | Anglais | Angle, phrases | Formule | Non publiables | Reprises | Temps total | Secondes par item |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `qwen2.5:3b` | 61 | 13.1 % | 1.6 % | 0.0 % | 19.7 % | 0.0 % | 19.7 % | 21 | 1177.7 s | 19.3 s |
| `qwen2.5:7b` | 61 | 6.6 % | 3.3 % | 0.0 % | 0.0 % | 0.0 % | 4.9 % | 6 | 2001.1 s | 32.8 s |
| `llama3.2:3b` | 61 | 0.0 % | 1.6 % | 0.0 % | 0.0 % | 0.0 % | 1.6 % | 1 | 943.9 s | 15.5 s |

## Interprétation

Les validateurs détectent des défauts de forme, pas la profondeur de l'analyse. Un modèle peut obtenir un faible taux de rejet tout en produisant un texte creux. La décision exige donc une lecture humaine à l'aveugle de `evaluation_aveugle.csv`. La clé est conservée séparément dans `cle_evaluation_aveugle.json`.

## Décision

Aucun changement de modèle de production n'est effectué par ce lot. Le choix revient à l'auteur du site après l'évaluation humaine.
