---
description: Standards SQL Snowflake et conventions dbt. Jinja2, CTEs, materialisation.
globs: "**/*.sql,**/*.yml"
---

- Mots-cles SQL en UPPERCASE : `SELECT`, `FROM`, `WHERE`, `JOIN`, `ORDER BY`
- CTEs (`WITH ... AS`) pour structurer les transformations
- Un CTE par etape logique (source, dedup, transform, final)
- Pas de sous-requetes imbriquees, toujours des CTEs
- `{{ source() }}` pour les references aux tables RAW
- `{{ ref() }}` pour les references entre modeles dbt
- `{{ config() }}` en haut de chaque modele
- Incremental merge : `unique_key`, `incremental_strategy='merge'`
- `is_incremental()` pour filtrer les nouvelles donnees
- Tags obligatoires : `staging` ou `marts` + nom de table
- Schema explicite dans `config()` : `STAGING` ou `MARTS`
- Jinja2 : `{{ }}` pour expressions, `{% %}` pour logique
- Macros partagees dans `dbt/macros/`
- `COALESCE()` pour les valeurs par defaut
- `NULLIF()` pour eviter les divisions par zero
