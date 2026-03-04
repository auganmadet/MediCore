# Security — MediCore ELT Pipeline

## Architecture de sécurité

### 1. Masquage PII (RGPD)

- Données personnelles masquées dans la couche staging via macro dbt centralisée
- Macro : `{{ pii_mask('column', 'PREFIX', hash_length=4) }}` dans `dbt/macros/pii_masking.sql`
- Génère : `'PREFIX_' || LEFT(MD5(CAST(col AS VARCHAR)), 4)`
- Modèles utilisant la macro :
  - `stg_fournisseurs` : FOU_NOM (prefix FOU), FOU_ADRESSE (prefix ADDR)
  - `stg_pharmacie` : PHA_NOM (prefix PHARM)
  - `stg_pharmacies` : name (prefix PHARM)
  - `stg_orders` : ORD_OPERATEUR (prefix USER)
  - `stg_mediprix_factures` : ORD_OPERATEUR (prefix USER), PHA_NOM (prefix PHARM)
- RAW conserve les données brutes (accès restreint au rôle MEDICORE_RAW_WRITER)
- STAGING et MARTS : aucune PII en clair

### 2. Gestion des credentials

- Tous les credentials dans `.env` (non versionné, dans `.gitignore`)
- Template : `.env.example` (versionné, sans valeurs sensibles)
- Variables d'environnement : `SNOWFLAKE_*`, `MYSQL_*`, `KAFKA_*`, `TEAMS_WEBHOOK_URL`
- Jamais de credentials dans le code source
- `python-dotenv` pour le chargement local
- Docker Compose `env_file` pour les conteneurs
- **Purge historique git** : effectuée avec `git-filter-repo` (4 secrets purgés : 2 Snowflake, 1 MySQL, 1 Teams webhook)
- **Rotation requise** : après toute purge git, les credentials exposés doivent être considérés compromis et rotés manuellement

### 3. Isolation des acces Snowflake

- **Roles RBAC** :
  - `MEDICORE_RAW_WRITER` : ecriture RAW uniquement
  - `MEDICORE_DBT_EXECUTOR` : lecture RAW, ecriture STAGING/MARTS/AUDIT/SNAPSHOTS
  - `MEDICORE_ANALYST` : lecture MARTS/AUDIT uniquement
- **Users de service** :
  - `MEDICORE_DBT` : user principal pour dbt/pipelines (default role = MEDICORE_DBT_EXECUTOR)
  - `MEDICORE_DBT_SVC` : user secondaire pour CI/CD
- **Warehouse** : `MEDICORE_WH` (XSMALL, auto-suspend 60s)
- **Database** : `MEDICORE` avec schemas RAW, STAGING, MARTS, AUDIT, SNAPSHOTS
- **Grants** : DDL complet dans `scripts/DDL_WH.sql` (CREATE SCHEMA + GRANT + FUTURE TABLES)
- **Ownership** : les tables RAW sont owned par `MEDICORE_RAW_WRITER` (ACCOUNTADMIN ne peut pas les ALTER directement)

### 4. Authentication Policy (MFA)

- **Policy** : `MEDICORE_TEMP.AUTH_POLICIES.MEDICORE_NO_MFA_REQUIRED`
- **Objectif** : Desactiver MFA obligatoire pour connexions programmatiques
- **Attachee au** : Compte (tous les users en beneficient)
- **Pourquoi** : Sans cette policy, les connexions Python/dbt/snowsql echouent car pas de prompt MFA possible en mode batch
- **Config** :
  - `MFA_ENROLLMENT = OPTIONAL`
  - `AUTHENTICATION_METHODS = (ALL)`
  - `CLIENT_TYPES = (ALL)`
- **DDL** : Cree dans `scripts/DDL_WH.sql` section 1

### 5. Protection SQL injection

- Pipelines Python : requêtes paramétrées ou ORM Snowflake
- dbt : `{{ source() }}` et `{{ ref() }}` (pas de SQL dynamique brut)
- Pas d'interpolation de chaînes dans les requêtes SQL
- Inputs utilisateur inexistants (pipeline batch, pas d'UI)

### 6. Securite CDC / Kafka

- Debezium : accès lecture seule au binlog MySQL
- Kafka : communication interne Docker network uniquement
- DLQ : events malformés isolés (pas de perte silencieuse)
- Commit offset manuel : pas de perte de données en cas d'échec

### 7. Monitoring et audit

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
