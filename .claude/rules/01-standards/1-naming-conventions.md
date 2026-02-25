---
description: Conventions de nommage PEP 8 et SQL appliquées systématiquement.
---

- Python `snake_case` : fonctions, méthodes, variables
- Python `PascalCase` : classes
- Python `UPPER_SNAKE_CASE` : constantes
- Préfixer booléens : `is_`, `has_`, `should_`
- Préfixer méthodes privées : `_`
- Verbes pour les actions, noms pour les valeurs
- Pas d'abréviations sauf courantes (db, id, url, config, sf, dbt)
- Pas de noms à une lettre (sauf boucles `i`, `j`)
- Noms révélant l'intention
- Cohérence dans tout le projet
- SQL : `UPPERCASE` pour mots-clés (SELECT, FROM, WHERE, JOIN)
- SQL : `snake_case` pour noms de colonnes dbt
- SQL : préfixe `stg_` pour staging, `dim_` pour dimensions, `fact_` pour faits
- SQL : préfixe `mart_kpi_` pour les KPIs métier
- dbt : tags descriptifs (`staging`, `marts`, `high_volume`, `incremental`)
