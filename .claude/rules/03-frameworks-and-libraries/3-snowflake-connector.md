---
description: Patterns snowflake-connector-python. Connexion, COPY INTO, stages, bulk insert.
globs: "pipelines/**/*.py"
---

- `snowflake.connector.connect()` avec rôle `MEDIcore_DBT_EXECUTOR`
- Database `MEDIcore`, warehouse `MEDIcore_WH`, schéma `RAW`
- Credentials via `os.getenv()` : `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`
- Bulk load : Parquet -> `PUT @stage` -> `COPY INTO`
- Chunking pandas DataFrames pour les gros volumes
- `cursor.execute()` pour les requêtes DDL/DML
- `cursor.executemany()` pour les inserts batch CDC
- Fermeture connexion dans `finally` ou context manager
- `CLUSTER BY (cdc_timestamp)` sur les tables CDC RAW
- `TRUNCATE` avant reload des tables référence
- `CREATE TABLE IF NOT EXISTS` pour les tables DLQ
- Paramètres de connexion jamais en dur dans le code
- Gestion des erreurs de connexion avec retry
- JAMAIS `sf_conn.cursor().execute()` en boucle — chaque appel crée un curseur qui fuit (OOM après 100+ itérations). Toujours réutiliser un seul curseur
- `FORCE = TRUE` dans COPY INTO après TRUNCATE — le load metadata persiste 64 jours et les fichiers sont silencieusement skippés sinon
- MySQL TINYINT 0/1 → Parquet int → Snowflake refuse `variant→BOOLEAN`. Détecter via `DESCRIBE TABLE`, convertir `df[col].astype(bool)` avant `.to_parquet()`
- `gc.collect()` + `del df, rows` après chaque chunk Parquet pour éviter la fragmentation mémoire (chunk 500K rows max pour 7.5 GiB)
