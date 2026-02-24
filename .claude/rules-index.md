# Rules Index — MediCore ELT Pipeline

Index de toutes les regles disponibles dans `.claude/rules/`.
Claude Code charge automatiquement les regles par matching de globs.

## Regles universelles [ALWAYS]

Ces regles sont chargees systematiquement avant toute tache (pas de globs).

| Fichier | Description |
|---------|-------------|
| `01-standards/1-clean-code.md` | Principes de code propre, lisibilite, limites de taille |
| `01-standards/1-naming-conventions.md` | Conventions PEP 8 + SQL : snake_case, PascalCase, UPPER_SNAKE_CASE |
| `05-workflows-and-processes/5-git-workflow.md` | Commits francais, branches, historique |
| `05-workflows-and-processes/5-bug-investigation.md` | Processus investigation et correction bugs |

## Regles contextuelles

Chargees automatiquement selon les fichiers impliques dans la tache.

| Fichier | Description | Globs |
|---------|-------------|-------|
| **Architecture** | | |
| `00-architecture/0-elt-pipeline-architecture.md` | Pipeline ELT, couches, flux de donnees | `pipelines/**/*.py`, `dbt/**/*.sql` |
| **Standards** | | |
| `01-standards/1-python-code-standards.md` | PEP 8, imports, docstrings, logging | `**/*.py` |
| **Langages** | | |
| `02-programming-languages/2-python-advanced.md` | Type hints, gestion d'erreurs, patterns Python | `**/*.py` |
| `02-programming-languages/2-sql-dbt-standards.md` | SQL Snowflake, Jinja2, conventions dbt | `**/*.sql`, `**/*.yml` |
| **Frameworks** | | |
| `03-frameworks-and-libraries/3-snowflake-connector.md` | snowflake-connector-python, COPY INTO, stages | `pipelines/**/*.py` |
| `03-frameworks-and-libraries/3-mysql-connector.md` | mysql.connector, streaming, timeouts, chunking | `pipelines/bulk_load.py` |
| `03-frameworks-and-libraries/3-kafka-cdc.md` | kafka-python, Debezium, micro-batch, DLQ | `pipelines/daily_cdc_batch.py` |
| `03-frameworks-and-libraries/3-dbt-models.md` | dbt incremental, merge, macros, tags | `dbt/**/*.sql`, `dbt/**/*.yml` |
| **Outils** | | |
| `04-tools-and-configurations/4-project-structure.md` | Structure projet, organisation fichiers | `**/*.py`, `**/*.sql` |
| `04-tools-and-configurations/4-docker-infrastructure.md` | Docker Compose, services, health checks | `docker-compose.yml`, `Dockerfile`, `scripts/**` |
| **Qualite** | | |
| `07-quality-assurance/7-dbt-testing.md` | Tests dbt, freshness, data quality | `dbt/**/*.yml`, `dbt/**/*.sql` |
| **Domaine** | | |
| `08-domain-specific-rules/8-pharmacy-data-model.md` | Tables, dimensions, faits, KPIs pharmacie | `dbt/models/**/*.sql` |
| `08-domain-specific-rules/8-pii-masking.md` | Masquage PII, RGPD, MD5 | `dbt/macros/**/*.sql`, `dbt/models/staging/**/*.sql` |
| `08-domain-specific-rules/8-cdc-data-integrity.md` | Integrite CDC, dedup, DLQ, recovery | `pipelines/**/*.py`, `dbt/models/staging/**/*.sql` |
| **Meta** | | |
| `meta-generator.md` | Template de creation de nouvelles regles | `.claude/rules/**` |
