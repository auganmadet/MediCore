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
-- SECTION 3 : DATABASE ET SCHEMAS
-- ============================================================================

CREATE OR REPLACE DATABASE MEDICORE
    COMMENT = 'Database MEDICORE - Pharmacie analytics';

USE DATABASE MEDICORE;

CREATE OR REPLACE SCHEMA RAW
    COMMENT = 'RAW layer - Donnees brutes MySQL CDC vers Kafka';

CREATE OR REPLACE SCHEMA STAGING
    COMMENT = 'STAGING layer - Donnees nettoyees/dedupliquees';

CREATE OR REPLACE SCHEMA MARTS
    COMMENT = 'MARTS layer - Dimensions et faits analytiques';

CREATE OR REPLACE SCHEMA AUDIT
    COMMENT = 'AUDIT layer - Suivi des runs dbt et metriques qualite';

CREATE OR REPLACE SCHEMA SNAPSHOTS
    COMMENT = 'SNAPSHOTS layer - Tables SCD2 pour historisation';

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
-- SECTION 12 : TABLES AUDIT (pour on-run-end dbt)
-- ============================================================================

CREATE TABLE IF NOT EXISTS MEDICORE.AUDIT.PIPELINE_RUNS (
    RUN_ID VARCHAR(36) PRIMARY KEY,
    ENV VARCHAR(10),
    RUN_START TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    RUN_END TIMESTAMP_NTZ,
    STATUS VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS MEDICORE.AUDIT.PIPELINE_STEP_RUNS (
    RUN_ID VARCHAR(36),
    STEP_NAME VARCHAR(50),
    STEP_START TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    STEP_END TIMESTAMP_NTZ,
    STATUS VARCHAR(20),
    ROWS_PROCESSED NUMBER,
    ERROR_MESSAGE VARCHAR(1000)
);

CREATE TABLE IF NOT EXISTS MEDICORE.AUDIT.DBT_MODEL_RUNS (
    RUN_ID VARCHAR(36),
    MODEL_NAME VARCHAR(100),
    STATUS VARCHAR(20),
    ROWS_AFFECTED NUMBER,
    EXECUTION_TIME_SEC FLOAT,
    CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ============================================================================
-- SECTION 13 : VERIFICATION
-- ============================================================================

SELECT 'MEDICORE DDL SUCCESS - Infrastructure prete' AS status;

-- Verification des grants
SHOW GRANTS TO ROLE MEDICORE_RAW_WRITER;
SHOW GRANTS TO ROLE MEDICORE_DBT_EXECUTOR;
SHOW GRANTS TO ROLE MEDICORE_ANALYST;

-- Verification authentication policy
SHOW AUTHENTICATION POLICIES IN ACCOUNT;
