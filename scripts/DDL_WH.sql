-- ============================================================================
-- DDL_WH.sql - Setup complet Snowflake pour MediCore ELT Pipeline
-- Usage: snowsql -c medicore_admin -f scripts/DDL_WH.sql
-- ============================================================================

-- 0. Utiliser un role admin
USE ROLE ACCOUNTADMIN;

-- 1. Utiliser le warehouse par defaut COMPUTE_WH (existant)
USE WAREHOUSE COMPUTE_WH;

-- ============================================================================
-- SECTION 1 : AUTHENTICATION POLICY (NO MFA pour connexions programmatiques)
-- ============================================================================

-- 1.1 Creer database temporaire pour heberger l'authentication policy
CREATE DATABASE IF NOT EXISTS MEDICORE_TEMP
    COMMENT = 'Database technique pour authentication policies';

CREATE SCHEMA IF NOT EXISTS MEDICORE_TEMP.AUTH_POLICIES
    COMMENT = 'Schema pour authentication policies';

-- 1.2 Creer authentication policy sans MFA obligatoire
-- CRITIQUE : Sans cette policy, les connexions Python/dbt/snowsql echouent
CREATE OR REPLACE AUTHENTICATION POLICY MEDICORE_TEMP.AUTH_POLICIES.MEDICORE_NO_MFA_REQUIRED
    AUTHENTICATION_METHODS = (ALL)
    CLIENT_TYPES = (ALL)
    MFA_ENROLLMENT = OPTIONAL
    COMMENT = 'MFA optionnel pour connexions programmatiques (dbt, Python, snowsql)';

-- 1.3 Attacher la policy au compte (tous les users en beneficient)
ALTER ACCOUNT SET AUTHENTICATION POLICY = MEDICORE_TEMP.AUTH_POLICIES.MEDICORE_NO_MFA_REQUIRED;

-- 1.4 Desactiver explicitement MFA pour l'utilisateur principal
ALTER USER AUGUSTIN SET DISABLE_MFA = TRUE;

-- ============================================================================
-- SECTION 2 : WAREHOUSE
-- ============================================================================

CREATE OR REPLACE WAREHOUSE MEDICORE_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Warehouse MEDICORE ELT pipeline';

-- ============================================================================
-- SECTION 3 : DATABASES ET SCHEMAS (multi-environnement)
-- ============================================================================

-- 3a. Database PRODUCTION
CREATE DATABASE IF NOT EXISTS MEDICORE_PROD
    COMMENT = 'PRODUCTION - Pipeline ELT pharmacie, lu par Metabase';

USE DATABASE MEDICORE_PROD;

CREATE SCHEMA IF NOT EXISTS RAW
    COMMENT = 'RAW layer - Donnees brutes MySQL CDC vers Kafka';

CREATE SCHEMA IF NOT EXISTS STAGING
    COMMENT = 'STAGING layer - Donnees nettoyees/dedupliquees';

CREATE SCHEMA IF NOT EXISTS MARTS
    COMMENT = 'MARTS layer - Dimensions et faits analytiques';

CREATE SCHEMA IF NOT EXISTS AUDIT
    COMMENT = 'AUDIT layer - Suivi des runs dbt et metriques qualite';

CREATE SCHEMA IF NOT EXISTS SNAPSHOTS
    COMMENT = 'SNAPSHOTS layer - Tables SCD2 pour historisation';

-- 3b. Database DEVELOPPEMENT (clone de prod, zero-copy)
CREATE DATABASE IF NOT EXISTS MEDICORE_DEV CLONE MEDICORE_PROD;

-- 3c. Database TEST (CI/CD GitHub Actions, alimentee par seeds dbt)
CREATE DATABASE IF NOT EXISTS MEDICORE_TEST;
CREATE SCHEMA IF NOT EXISTS MEDICORE_TEST.RAW;

-- ============================================================================
-- SECTION 4 : ROLES (RBAC)
-- ============================================================================

CREATE OR REPLACE ROLE MEDICORE_RAW_WRITER
    COMMENT = 'Role pour RAW CDC writer (Python bulk_load, daily_cdc_batch)';

CREATE OR REPLACE ROLE MEDICORE_DBT_EXECUTOR
    COMMENT = 'Role pour dbt executor : read RAW, write STAGING/MARTS/SNAPSHOTS';

CREATE OR REPLACE ROLE MEDICORE_ANALYST
    COMMENT = 'Role Analyst read-only sur MARTS';

-- ============================================================================
-- SECTION 5 : USERS DE SERVICE
-- ============================================================================

-- 5.1 User principal pour dbt/pipelines
CREATE USER IF NOT EXISTS MEDICORE_DBT
    PASSWORD = 'CHANGE_ME_IMMEDIATELY'
    DEFAULT_WAREHOUSE = MEDICORE_WH
    DEFAULT_ROLE = MEDICORE_DBT_EXECUTOR
    MUST_CHANGE_PASSWORD = FALSE
    COMMENT = 'Service account pour dbt et pipelines Python';

-- 5.2 User de service secondaire (CI/CD ou environnement separe)
CREATE USER IF NOT EXISTS MEDICORE_DBT_SVC
    PASSWORD = 'CHANGE_ME_IMMEDIATELY'
    DEFAULT_WAREHOUSE = MEDICORE_WH
    DEFAULT_ROLE = MEDICORE_DBT_EXECUTOR
    MUST_CHANGE_PASSWORD = FALSE
    COMMENT = 'Service account secondaire (CI/CD)';

-- ============================================================================
-- SECTION 6 : GRANTS WAREHOUSE
-- ============================================================================

ALTER WAREHOUSE MEDICORE_WH RESUME;
USE WAREHOUSE MEDICORE_WH;

GRANT USAGE, MONITOR ON WAREHOUSE MEDICORE_WH TO ROLE MEDICORE_RAW_WRITER;
GRANT USAGE, MONITOR ON WAREHOUSE MEDICORE_WH TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT USAGE ON WAREHOUSE MEDICORE_WH TO ROLE MEDICORE_ANALYST;

-- ============================================================================
-- SECTION 7 : GRANTS DATABASE
-- ============================================================================

GRANT USAGE ON DATABASE MEDICORE TO ROLE MEDICORE_RAW_WRITER;
GRANT USAGE, CREATE SCHEMA ON DATABASE MEDICORE TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT USAGE ON DATABASE MEDICORE TO ROLE MEDICORE_ANALYST;

-- ============================================================================
-- SECTION 8 : GRANTS SCHEMAS
-- ============================================================================

-- RAW : ecriture pour CDC writer, lecture pour dbt
GRANT ALL PRIVILEGES ON SCHEMA RAW TO ROLE MEDICORE_RAW_WRITER;
GRANT USAGE ON SCHEMA RAW TO ROLE MEDICORE_DBT_EXECUTOR;

-- STAGING : ecriture pour dbt
GRANT ALL PRIVILEGES ON SCHEMA STAGING TO ROLE MEDICORE_DBT_EXECUTOR;

-- MARTS : ecriture pour dbt, lecture pour analysts
GRANT ALL PRIVILEGES ON SCHEMA MARTS TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT USAGE ON SCHEMA MARTS TO ROLE MEDICORE_ANALYST;

-- AUDIT : ecriture pour dbt, lecture pour analysts
GRANT ALL PRIVILEGES ON SCHEMA AUDIT TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT USAGE ON SCHEMA AUDIT TO ROLE MEDICORE_ANALYST;

-- SNAPSHOTS : ecriture pour dbt
GRANT ALL PRIVILEGES ON SCHEMA SNAPSHOTS TO ROLE MEDICORE_DBT_EXECUTOR;

-- ============================================================================
-- SECTION 9 : FUTURE GRANTS (tables/vues creees ulterieurement)
-- ============================================================================

-- RAW
GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON FUTURE TABLES IN SCHEMA RAW TO ROLE MEDICORE_RAW_WRITER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA RAW TO ROLE MEDICORE_DBT_EXECUTOR;

-- STAGING
GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON FUTURE TABLES IN SCHEMA STAGING TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA STAGING TO ROLE MEDICORE_DBT_EXECUTOR;

-- MARTS
GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON FUTURE TABLES IN SCHEMA MARTS TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT SELECT ON FUTURE TABLES IN SCHEMA MARTS TO ROLE MEDICORE_ANALYST;

-- AUDIT
GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON FUTURE TABLES IN SCHEMA AUDIT TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT SELECT ON FUTURE TABLES IN SCHEMA AUDIT TO ROLE MEDICORE_ANALYST;

-- SNAPSHOTS
GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON FUTURE TABLES IN SCHEMA SNAPSHOTS TO ROLE MEDICORE_DBT_EXECUTOR;

-- ============================================================================
-- SECTION 10 : GRANTS SUR TABLES EXISTANTES
-- ============================================================================

GRANT SELECT ON ALL TABLES IN SCHEMA RAW TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA STAGING TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA MARTS TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA AUDIT TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA SNAPSHOTS TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT SELECT ON ALL TABLES IN SCHEMA MARTS TO ROLE MEDICORE_ANALYST;
GRANT SELECT ON ALL TABLES IN SCHEMA AUDIT TO ROLE MEDICORE_ANALYST;

-- ============================================================================
-- SECTION 11 : ASSOCIATION ROLES -> USERS
-- ============================================================================

-- User humain (admin)
GRANT ROLE MEDICORE_RAW_WRITER TO USER AUGUSTIN;
GRANT ROLE MEDICORE_DBT_EXECUTOR TO USER AUGUSTIN;

-- Users de service
GRANT ROLE MEDICORE_RAW_WRITER TO USER MEDICORE_DBT;
GRANT ROLE MEDICORE_DBT_EXECUTOR TO USER MEDICORE_DBT;

GRANT ROLE MEDICORE_RAW_WRITER TO USER MEDICORE_DBT_SVC;
GRANT ROLE MEDICORE_DBT_EXECUTOR TO USER MEDICORE_DBT_SVC;

-- ============================================================================
-- SECTION 12 : TABLES AUDIT
-- ============================================================================
-- Les tables AUDIT sont définies dans DDL_TABLES.sql (source de vérité).
-- DDL_WH.sql crée uniquement le schéma, pas les tables.
-- Exécuter DDL_TABLES.sql après DDL_WH.sql pour créer les tables AUDIT.

-- ============================================================================
-- SECTION 13 : ROLES MULTI-ENVIRONNEMENT
-- ============================================================================

-- Role DEV (developpeurs, acces MEDICORE_DEV uniquement)
CREATE ROLE IF NOT EXISTS MEDICORE_DEV_EXECUTOR;
GRANT ALL ON DATABASE MEDICORE_DEV TO ROLE MEDICORE_DEV_EXECUTOR;
GRANT ALL ON ALL SCHEMAS IN DATABASE MEDICORE_DEV TO ROLE MEDICORE_DEV_EXECUTOR;
GRANT USAGE ON WAREHOUSE MEDICORE_WH TO ROLE MEDICORE_DEV_EXECUTOR;

-- Role TEST (CI GitHub Actions, acces MEDICORE_TEST uniquement)
CREATE ROLE IF NOT EXISTS MEDICORE_TEST_EXECUTOR;
GRANT ALL ON DATABASE MEDICORE_TEST TO ROLE MEDICORE_TEST_EXECUTOR;
GRANT ALL ON ALL SCHEMAS IN DATABASE MEDICORE_TEST TO ROLE MEDICORE_TEST_EXECUTOR;
GRANT USAGE ON WAREHOUSE MEDICORE_WH TO ROLE MEDICORE_TEST_EXECUTOR;

-- Hierarchie : DBT_EXECUTOR herite des roles DEV et TEST
GRANT ROLE MEDICORE_DEV_EXECUTOR TO ROLE MEDICORE_DBT_EXECUTOR;
GRANT ROLE MEDICORE_TEST_EXECUTOR TO ROLE MEDICORE_DBT_EXECUTOR;

-- ============================================================================
-- SECTION 14 : VERIFICATION
-- ============================================================================

SELECT 'MEDICORE DDL SUCCESS - Infrastructure prete' AS status;

-- Verification des grants
SHOW GRANTS TO ROLE MEDICORE_RAW_WRITER;
SHOW GRANTS TO ROLE MEDICORE_DBT_EXECUTOR;
SHOW GRANTS TO ROLE MEDICORE_ANALYST;

-- Verification authentication policy
SHOW AUTHENTICATION POLICIES IN ACCOUNT;
