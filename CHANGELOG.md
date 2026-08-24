# Changelog

Toutes les modifications notables apportées à ce projet sont consignées dans ce document.
Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

## [2026-08-24] Notification de publication sur mobile

### Ajouté
- `pipeline/rendre_notification_publication.py` : rédige la liste des items réellement publiés par une exécution (croisement de `_candidats_cures.json` et du flux après publication, pour ne pas annoncer un candidat archivé ou écarté).
- Titre d'issue rendu par le script (`_publication_du_jour_titre.txt`) : nombre d'entrées, date et premier titre, tronqué à 120 caractères. C'est l'objet du courriel envoyé par GitHub, seul canal utilisé ici puisque l'application mobile n'est pas installée.
- Étape de notification dans `.github/workflows/frontiere.yml` : ouvre une issue assignée à Ulrich avec les titres, les liens et les deux pages du site. L'assignation est ce qui déclenche l'alerte sur l'application GitHub mobile, comme dans `regenerer-flux.yml`. Le cron ne signalait jusqu'ici que ses échecs.
## [2026-08-24] Rattrapage bilingue de La Frontière

### Ajouté
- `pipeline/collecter_abstracts_manquants.py` : retélécharge l'abstract d'origine des items publiés qui ne l'ont plus localement (arXiv, NBER via OpenAlex puis le flux RSS, CEPR via son flux, Fed, DOI). Sans lui, ces items ne pouvaient pas recevoir de résumé anglais.
- Troisième source d'abstracts dans `regenerer_flux.charger_abstracts`, `_abstracts_rattrapage.json`, placée en dernier pour que le corpus figé garde la priorité.
- `pipeline/verifier_bilinguisme_flux.py` : échoue quand plus de 10 % des items publiés sont servis en français sur `/en/frontier/`. Branché sur le cron de La Frontière en `continue-on-error` et sur la suite de tests en CI.

### Retiré
- La note de langue en tête de `/en/frontier/`, posée le 19 août 2026 pour annoncer que des entrées n'avaient qu'un résumé français. Elle en visait 35 sur 60 ; il en reste une sur 62, la proportion est devenue négligeable et son propre commentaire prévoyait ce retrait. Le marquage `lang="fr"` par entrée, lui, subsiste : c'est le signal honnête pour l'entrée restante.

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

