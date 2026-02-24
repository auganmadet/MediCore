---
description: Standards SQL Snowflake et conventions dbt. Jinja2, CTEs, matérialisation.
globs: "**/*.sql,**/*.yml"
---

- Mots-clés SQL en UPPERCASE : `SELECT`, `FROM`, `WHERE`, `JOIN`, `ORDER BY`
- CTEs (`WITH ... AS`) pour structurer les transformations
- Un CTE par étape logique (source, dédup, transform, final)
- Pas de sous-requêtes imbriquées, toujours des CTEs
- `{{ source() }}` pour les références aux tables RAW
- `{{ ref() }}` pour les références entre modèles dbt
- `{{ config() }}` en haut de chaque modèle
- Incremental merge : `unique_key`, `incremental_strategy='merge'`
- `is_incremental()` pour filtrer les nouvelles données
- Tags obligatoires : `staging` ou `marts` + nom de table
- Schéma explicite dans `config()` : `STAGING` ou `MARTS`
- Jinja2 : `{{ }}` pour expressions, `{% %}` pour logique
- Macros partagées dans `dbt/macros/`
- `COALESCE()` pour les valeurs par défaut
- `NULLIF()` pour éviter les divisions par zéro
