---
description: Conventions de nommage PEP 8 et SQL appliquees systematiquement.
---

- Python `snake_case` : fonctions, methodes, variables
- Python `PascalCase` : classes
- Python `UPPER_SNAKE_CASE` : constantes
- Prefixer booleens : `is_`, `has_`, `should_`
- Prefixer methodes privees : `_`
- Verbes pour les actions, noms pour les valeurs
- Pas d'abbreviations sauf courantes (db, id, url, config, sf, dbt)
- Pas de noms a une lettre (sauf boucles `i`, `j`)
- Noms revelant l'intention
- Coherence dans tout le projet
- SQL : `UPPERCASE` pour mots-cles (SELECT, FROM, WHERE, JOIN)
- SQL : `snake_case` pour noms de colonnes dbt
- SQL : prefixe `stg_` pour staging, `dim_` pour dimensions, `fact_` pour faits
- SQL : prefixe `mart_kpi_` pour les KPIs metier
- dbt : tags descriptifs (`staging`, `marts`, `high_volume`, `incremental`)
