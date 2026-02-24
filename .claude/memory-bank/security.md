# Security — MediCore ELT Pipeline

## Architecture de securite

### 1. Masquage PII (RGPD)

- Donnees personnelles masquees par MD5 dans la couche staging
- Colonnes concernees : noms, adresses, telephones, emails
- Tables concernees : `stg_orders` (age, sexe, departement), `stg_pharmacie` (nom)
- Macro dbt : `{{ mask_pii('column_name') }}` dans `dbt/macros/pii_masking.sql`
- RAW conserve les donnees brutes (acces restreint)
- STAGING et MARTS : aucune PII en clair

### 2. Gestion des credentials

- Tous les credentials dans `.env` (non versionne, dans `.gitignore`)
- Variables d'environnement : `SNOWFLAKE_*`, `MYSQL_*`, `KAFKA_*`
- Jamais de credentials dans le code source
- `python-dotenv` pour le chargement local
- Docker Compose `env_file` pour les conteneurs

### 3. Isolation des acces Snowflake

- Role dedie : `MEDIcore_DBT_EXECUTOR`
- Warehouse dedie : `MEDIcore_WH` (XS dev, XL prod)
- Database : `MEDIcore` avec schemas RAW, STAGING, MARTS
- Grants minimaux : lecture RAW, ecriture STG/MARTS
- DDL dans `scripts/DDL_WH.sql`

### 4. Protection SQL injection

- Pipelines Python : requetes parametrees ou ORM Snowflake
- dbt : `{{ source() }}` et `{{ ref() }}` (pas de SQL dynamique brut)
- Pas d'interpolation de chaines dans les requetes SQL
- Inputs utilisateur inexistants (pipeline batch, pas d'UI)

### 5. Securite CDC / Kafka

- Debezium : acces lecture seule au binlog MySQL
- Kafka : communication interne Docker network uniquement
- DLQ : events malformes isoles (pas de perte silencieuse)
- Commit offset manuel : pas de perte de donnees en cas d'echec

### 6. Monitoring et audit

- Teams webhook : alertes sur echecs pipeline
- dbt source freshness : detection donnees obsoletes
- Docker health checks : disponibilite services
- Logs dans `audit/logs/` et `logs/`

## Points d'attention pour le developpement

- Ne jamais desactiver le masquage PII dans staging
- Ne jamais commiter `.env` ou fichiers contenant des credentials
- Toujours utiliser des requetes parametrees dans les pipelines Python
- Verifier le masquage PII apres ajout de toute nouvelle colonne sensible
- Maintenir le role Snowflake avec des grants minimaux
- Logger tout echec de pipeline avec contexte suffisant pour diagnostic
