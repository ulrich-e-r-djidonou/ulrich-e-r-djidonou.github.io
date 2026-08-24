# Changelog

Toutes les modifications notables apportées à ce projet sont consignées dans ce document.
Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

## [2026-08-24] Rattrapage bilingue de La Frontière

### Ajouté
- `pipeline/collecter_abstracts_manquants.py` : retélécharge l'abstract d'origine des items publiés qui ne l'ont plus localement (arXiv, NBER via OpenAlex puis le flux RSS, CEPR via son flux, Fed, DOI). Sans lui, ces items ne pouvaient pas recevoir de résumé anglais.
- Troisième source d'abstracts dans `regenerer_flux.charger_abstracts`, `_abstracts_rattrapage.json`, placée en dernier pour que le corpus figé garde la priorité.
- `pipeline/verifier_bilinguisme_flux.py` : échoue quand plus de 10 % des items publiés sont servis en français sur `/en/frontier/`. Branché sur le cron de La Frontière en `continue-on-error` et sur la suite de tests en CI.

### Corrigé
- 60 items sur 62 n'avaient pas de `resume_en` ou d'`angle_eco_en` et la page anglaise servait leur texte français. Le flux en compte désormais 61 sur 62 en anglais. Le seul restant, `AI Financial Advice: Supply, Demand, and Life Cycle Implications`, n'a plus d'abstract récupérable chez aucune des sources interrogées.
- Le JSON-LD de `en/frontier/index.html` annonçait `inLanguage: fr` sur 62 entrées ; il en annonce une seule aujourd'hui.
- Les tests de `charger_abstracts` laissaient fuir le vrai fichier du dépôt faute d'isoler la nouvelle source.

## [2026-08-24] Journalisation des validateurs

### Ajouté
- Journalisation détaillée sur `stderr` des motifs de rejet (`nombre_phrases`, `chiffre_invente`, `tiret_cadratin`, `premiere_personne`, etc.) dans `_generer_avec_reprise` de `pipeline/curate.py`, avec indication du nom de champ et du titre de l'article pour chaque essai.
- Fonction `mesurer_en` dans `pipeline/calibrer_validateurs.py` pour mesurer et rapporter la calibration des validateurs sur les champs anglais publiés (`resume_en`, `angle_eco_en`).
- Suite de tests unitaires `JournalisationValidationTests` dans `pipeline/test_curate.py` vérifiant la journalisation sur `stderr`, la gestion des reprises et la rétrocompatibilité (portant le total de la suite à 401 tests).

### Modifié
- `main()` dans `pipeline/curate.py` transmettant les validateurs d'erreurs enrichis et le contexte (`nom_champ`, `titre`) lors de chaque appel de rédaction.

