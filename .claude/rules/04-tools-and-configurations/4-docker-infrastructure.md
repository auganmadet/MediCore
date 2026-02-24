---
description: Infrastructure Docker Compose et services. Health checks, ressources, orchestration, alerting.
globs: "docker-compose.yml,Dockerfile,scripts/**"
---

- 6 services : medicore_elt_batch, mysql_cdc, kafka, zookeeper, connect, kafdrop
- Health checks sur tous les services
- Limites ressources : 8GB RAM, 2 CPUs pour le conteneur principal
- Multi-stage build : builder (pip install) + final (runtime)
- `entrypoint.sh` : attente services + dbt deps + cleanup locks
- `batch_loop.sh` : boucle principale (5 min dev / 30 min prod)
- `healthcheck.py` : vérification connectivité Snowflake
- `setup.sh` : premier lancement (DDL + Docker + Debezium connector)
- Variables d'environnement via `.env` et Docker Compose
- Volumes : persistance Kafka/Zookeeper data
- Network : communication inter-services via noms Docker
- Kafdrop pour monitoring visuel des topics Kafka
- Redémarrage automatique des services (`restart: unless-stopped`)
- JAMAIS `docker exec -d` sans vérifier `docker top` — les process détachés persistent et causent OOM + doublons COPY INTO. Utiliser `python -u` pour unbuffered stdout
- Fail-fast au démarrage : valider les credentials Snowflake (`healthcheck.py`) avant de lancer `batch_loop.sh`
- Teams webhook : format Adaptive Card JSON (pas de texte brut), retry 3 tentatives avec backoff exponentiel
- `TEAMS_WEBHOOK_URL` optionnel — si absent, log sans alerte
- Compteur d'échecs consécutifs par phase (`CDC_FAIL`, `STG_FAIL`, etc.), seuil configurable via `ALERT_THRESHOLD` (défaut 3)
- Notification recovery quand le compteur repasse à 0 après avoir atteint le seuil
- Orchestration bash : chaque phase dans `if commande; then ... else fail_count++; fi` — JAMAIS `|| echo` qui masque les erreurs
- Variable `ENV` (`dev`/`prod`) pilote : taille warehouse, intervalle batch, schéma dbt
- dbt `--target $ENV` dans toutes les commandes batch_loop.sh
- Jamais de credentials prod en dur — toujours via `.env`
