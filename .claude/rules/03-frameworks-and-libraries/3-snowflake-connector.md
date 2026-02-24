---
description: Patterns snowflake-connector-python. Connexion, COPY INTO, stages, bulk insert.
globs: "pipelines/**/*.py"
---

- `snowflake.connector.connect()` avec role `MEDIcore_DBT_EXECUTOR`
- Database `MEDIcore`, warehouse `MEDIcore_WH`, schema `RAW`
- Credentials via `os.getenv()` : `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`
- Bulk load : Parquet -> `PUT @stage` -> `COPY INTO`
- Chunking pandas DataFrames pour les gros volumes
- `cursor.execute()` pour les requetes DDL/DML
- `cursor.executemany()` pour les inserts batch CDC
- Fermeture connexion dans `finally` ou context manager
- `CLUSTER BY (cdc_timestamp)` sur les tables CDC RAW
- `TRUNCATE` avant reload des tables reference
- `CREATE TABLE IF NOT EXISTS` pour les tables DLQ
- Parametres de connexion jamais en dur dans le code
- Gestion des erreurs de connexion avec retry
- JAMAIS `sf_conn.cursor().execute()` en boucle — chaque appel cree un curseur qui fuit (OOM apres 100+ iterations). Toujours reutiliser un seul curseur
- `FORCE = TRUE` dans COPY INTO apres TRUNCATE — le load metadata persiste 64 jours et les fichiers sont silencieusement skippes sinon
- MySQL TINYINT 0/1 → Parquet int → Snowflake refuse `variant→BOOLEAN`. Detecter via `DESCRIBE TABLE`, convertir `df[col].astype(bool)` avant `.to_parquet()`
- `gc.collect()` + `del df, rows` apres chaque chunk Parquet pour eviter la fragmentation memoire (chunk 500K rows max pour 7.5 GiB)
