# Security — MediCore ELT Pipeline

## Architecture de sécurité

### 1. Masquage PII (RGPD)

- Données personnelles masquées par MD5 dans la couche staging
- Colonnes concernées : noms, adresses, téléphones, emails
- Tables concernées : `stg_orders` (âge, sexe, département), `stg_pharmacie` (nom)
- Macro dbt : `{{ mask_pii('column_name') }}` dans `dbt/macros/pii_masking.sql`
- RAW conserve les données brutes (accès restreint)
- STAGING et MARTS : aucune PII en clair

### 2. Gestion des credentials

- Tous les credentials dans `.env` (non versionné, dans `.gitignore`)
- Variables d'environnement : `SNOWFLAKE_*`, `MYSQL_*`, `KAFKA_*`
- Jamais de credentials dans le code source
- `python-dotenv` pour le chargement local
- Docker Compose `env_file` pour les conteneurs

### 3. Isolation des accès Snowflake

- Rôle dédié : `MEDIcore_DBT_EXECUTOR`
- Warehouse dédié : `MEDIcore_WH` (XS dev, XL prod)
- Database : `MEDIcore` avec schémas RAW, STAGING, MARTS
- Grants minimaux : lecture RAW, écriture STG/MARTS
- DDL dans `scripts/DDL_WH.sql`

### 4. Protection SQL injection

- Pipelines Python : requêtes paramétrées ou ORM Snowflake
- dbt : `{{ source() }}` et `{{ ref() }}` (pas de SQL dynamique brut)
- Pas d'interpolation de chaînes dans les requêtes SQL
- Inputs utilisateur inexistants (pipeline batch, pas d'UI)

### 5. Sécurité CDC / Kafka

- Debezium : accès lecture seule au binlog MySQL
- Kafka : communication interne Docker network uniquement
- DLQ : events malformés isolés (pas de perte silencieuse)
- Commit offset manuel : pas de perte de données en cas d'échec

### 6. Monitoring et audit

- Teams webhook : alertes sur échecs pipeline
- dbt source freshness : détection données obsolètes
- Docker health checks : disponibilité services
- Logs dans `audit/logs/` et `logs/`

## Points d'attention pour le développement

- Ne jamais désactiver le masquage PII dans staging
- Ne jamais commiter `.env` ou fichiers contenant des credentials
- Toujours utiliser des requêtes paramétrées dans les pipelines Python
- Vérifier le masquage PII après ajout de toute nouvelle colonne sensible
- Maintenir le rôle Snowflake avec des grants minimaux
- Logger tout échec de pipeline avec contexte suffisant pour diagnostic
