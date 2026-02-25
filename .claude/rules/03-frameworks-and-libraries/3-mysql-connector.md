---
description: Patterns mysql.connector pour bulk load MySQL. Streaming, timeouts, chunking.
globs: "pipelines/bulk_load.py"
---

- JAMAIS `pd.read_sql(chunksize=)` avec `mysql.connector` — bufférise l'intégralité du resultset en mémoire avant de chunker
- Utiliser `cursor(buffered=False)` + `fetchmany(chunk_size)` pour streaming server-side réel
- Timeouts obligatoires pour les longs loads : `wait_timeout=28800`, `net_read_timeout=600`, `net_write_timeout=600`
- Connexion via `mysql.connector.connect()` avec credentials depuis `os.getenv()`
- Fermer cursor et connexion dans `finally`
- Chunk size 500K rows pour rester sous 7.5 GiB de mémoire conteneur
