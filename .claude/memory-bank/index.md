# Memory Bank — MediCore ELT Pipeline

Organisation de la documentation projet par niveaux de priorite.

## Tier 1 — Contexte general

Charger systematiquement pour toute nouvelle tache ou feature.

| Document | Contenu |
|----------|---------|
| `getting-started.md` | Installation, configuration, lancement rapide |
| `architecture.md` | Pipeline ELT, couches, flux de donnees, services Docker |

## Tier 2 — Domaine et developpement

Charger pour les taches liees au domaine metier ou au workflow de developpement.

| Document | Contenu |
|----------|---------|
| `data-model.md` | Schema Snowflake, tables RAW/STG/MARTS, star schema |
| `tech-stack.md` | Technologies, versions, dependances |
| `development.md` | Workflow de developpement, commandes, conventions |
| `security.md` | PII masking, credentials, RGPD, isolation |

## Tier 3 — Fonctionnalites specifiques

Charger uniquement en cas de travail direct sur la fonctionnalite concernee.

| Document | Contenu |
|----------|---------|
| `cdc-integration.md` | Debezium, Kafka, micro-batch, DLQ, offset |
| `dbt-transformations.md` | Modeles staging/marts, incremental, macros, tests |
