# Changelog

Toutes les modifications notables apportées à ce projet sont consignées dans ce document.
Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

## [2026-08-24]

### Ajouté
- Journalisation détaillée sur `stderr` des motifs de rejet (`nombre_phrases`, `chiffre_invente`, `tiret_cadratin`, `premiere_personne`, etc.) dans `_generer_avec_reprise` de `pipeline/curate.py`, avec indication du nom de champ et du titre de l'article pour chaque essai.
- Fonction `mesurer_en` dans `pipeline/calibrer_validateurs.py` pour mesurer et rapporter la calibration des validateurs sur les champs anglais publiés (`resume_en`, `angle_eco_en`).
- Suite de tests unitaires `JournalisationValidationTests` dans `pipeline/test_curate.py` vérifiant la journalisation sur `stderr`, la gestion des reprises et la rétrocompatibilité (portant le total de la suite à 401 tests).

### Modifié
- `main()` dans `pipeline/curate.py` transmettant les validateurs d'erreurs enrichis et le contexte (`nom_champ`, `titre`) lors de chaque appel de rédaction.

