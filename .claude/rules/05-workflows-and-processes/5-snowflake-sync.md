---
description: Synchronisation bidirectionnelle Snowflake ↔ Code. Toute modif DDL doit être reflétée dans le code et inversement.
globs: "scripts/DDL_*.sql,dbt/profiles.yml,pipelines/**/*.py,scripts/batch_loop.sh,dbt/models/audit/**/*.sql,dbt/macros/persist_dbt_results.sql"
---

- Toute modification Snowflake (DDL, GRANT, database, schéma) DOIT être répercutée dans le code
- Toute modification du code référençant Snowflake DOIT être vérifiée côté Snowflake
- Ne jamais hardcoder `MEDICORE_PROD` dans les modèles dbt — utiliser `{{ target.database }}` pour les références cross-schema (AUDIT)
- Fichiers impactés : `DDL_WH.sql`, `DDL_TABLES.sql`, `profiles.yml`, `.env`, `batch_loop.sh`, `bulk_load.py`, `daily_cdc_batch.py`, `audit.py`, modèles `dbt/models/audit/*`, macro `persist_dbt_results.sql`
- Vérifier avec : `grep -r "MEDICORE" --include="*.{py,sql,sh,yml}" | grep -v node_modules | grep -v .venv`
- `DDL_TABLES.sql` et `DDL_WH.sql` hardcodent `MEDICORE_PROD` (scripts DDL one-shot, pas multi-env) — c'est attendu pour ces fichiers uniquement
