# Memory Bank — MediCore ELT Pipeline

Organisation de la documentation projet par niveaux de priorité.

## Tier 1 — Contexte général

Charger systématiquement pour toute nouvelle tâche ou feature.

  ┌──────────────────────┬─────────────────────────────────────────────────────────┐
  │       Document       │                         Contenu                         │
  ├──────────────────────┼─────────────────────────────────────────────────────────┤
  │ `getting-started.md` │ Installation, configuration, lancement rapide           │
  ├──────────────────────┼─────────────────────────────────────────────────────────┤
  │ `architecture.md`    │ Pipeline ELT, couches, flux de données, services Docker │
  └──────────────────────┴─────────────────────────────────────────────────────────┘

## Tier 2 — Domaine et développement

Charger pour les tâches liées au domaine métier ou au workflow de développement.

  ┌──────────────────┬─────────────────────────────────────────────────────┐
  │     Document     │                       Contenu                       │
  ├──────────────────┼─────────────────────────────────────────────────────┤
  │ `data-model.md`  │ Schéma Snowflake, tables RAW/STG/MARTS, star schema │
  ├──────────────────┼─────────────────────────────────────────────────────┤
  │ `tech-stack.md`  │ Technologies, versions, dépendances                 │
  ├──────────────────┼─────────────────────────────────────────────────────┤
  │ `development.md` │ Workflow de développement, commandes, conventions   │
  ├──────────────────┼─────────────────────────────────────────────────────┤
  │ `security.md`    │ PII masking, credentials, RGPD, isolation           │
  └──────────────────┴─────────────────────────────────────────────────────┘

## Tier 3 — Fonctionnalités spécifiques

Charger uniquement en cas de travail direct sur la fonctionnalité concernée.

  ┌──────────────────────────┬───────────────────────────────────────────────────┐
  │         Document         │                      Contenu                      │
  ├──────────────────────────┼───────────────────────────────────────────────────┤
  │ `cdc-integration.md`     │ Debezium, Kafka, micro-batch, DLQ, offset         │
  ├──────────────────────────┼───────────────────────────────────────────────────┤
  │ `dbt-transformations.md` │ Modèles staging/marts, incremental, macros, tests │
  └──────────────────────────┴───────────────────────────────────────────────────┘
