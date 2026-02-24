---
description: Structure du projet et organisation des fichiers.
globs: "**/*.py,**/*.sql"
---

- `pipelines/` : scripts Python d'ingestion (CDC, bulk load)
- `pipelines/utils/` : utilitaires partages (PII masking)
- `dbt/models/staging/` : modeles staging (dedup + PII)
- `dbt/models/marts/` : dimensions, faits, KPIs
- `dbt/macros/` : macros partagees (PII masking, log summary)
- `dbt/snapshots/` : snapshots SCD2 (historisation dimensions)
- `scripts/` : orchestration bash (batch_loop, setup, entrypoint)
- `docs/` : documentation fonctionnelle (KPIs, architecture)
- Config via `.env` et Docker Compose (non versionne)
- DDL Snowflake dans `scripts/DDL_TABLES.sql`
- Pas de fichiers de configuration hardcodes
