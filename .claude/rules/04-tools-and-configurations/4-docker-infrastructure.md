---
description: Infrastructure Docker Compose et services. Health checks, ressources, orchestration.
globs: "docker-compose.yml,Dockerfile,scripts/**"
---

- 6 services : medicore_elt_batch, mysql_cdc, kafka, zookeeper, connect, kafdrop
- Health checks sur tous les services
- Limites ressources : 8GB RAM, 2 CPUs pour le conteneur principal
- Multi-stage build : builder (pip install) + final (runtime)
- `entrypoint.sh` : attente services + dbt deps + cleanup locks
- `batch_loop.sh` : boucle principale (5 min dev / 30 min prod)
- `healthcheck.py` : verification connectivite Snowflake
- `setup.sh` : premier lancement (DDL + Docker + Debezium connector)
- Variables d'environnement via `.env` et Docker Compose
- Volumes : persistance Kafka/Zookeeper data
- Network : communication inter-services via noms Docker
- Kafdrop pour monitoring visuel des topics Kafka
- Redemarrage automatique des services (`restart: unless-stopped`)
- JAMAIS `docker exec -d` sans verifier `docker top` — les process detaches persistent et causent OOM + doublons COPY INTO. Utiliser `python -u` pour unbuffered stdout
- Fail-fast au demarrage : valider les credentials Snowflake (`healthcheck.py`) avant de lancer `batch_loop.sh`
