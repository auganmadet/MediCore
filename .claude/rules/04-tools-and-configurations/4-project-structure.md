---
description: Structure du projet et organisation des fichiers.
globs: "**/*.py,**/*.sql"
---

- `pipelines/` : scripts Python d'ingestion (CDC, bulk load)
- `pipelines/utils/` : utilitaires partagés (PII masking)
- `dbt/models/staging/` : modèles staging (dédup + PII)
- `dbt/models/marts/` : dimensions, faits, KPIs
- `dbt/macros/` : macros partagées (PII masking, log summary)
- `dbt/snapshots/` : snapshots SCD2 (historisation dimensions)
- `scripts/` : orchestration bash (batch_loop, setup, entrypoint)
- `docs/` : documentation fonctionnelle (KPIs, architecture)
- Config via `.env` et Docker Compose (non versionné)
- DDL Snowflake dans `scripts/DDL_TABLES.sql`
- Pas de fichiers de configuration hardcodés
