-- 0. Utiliser un rôle admin
USE ROLE ACCOUNTADMIN;

-- 1. Créer le Warehouse (taille SMALL pour tests, scale à MEDIUM/LARGE en prod)
CREATE OR REPLACE WAREHOUSE MEDIcore_WH
    WAREHOUSE_SIZE = 'SMALL'
    WAREHOUSE_PADDING_POLICY = 'STANDARD'
    AUTO_SUSPEND = 300		-- arrêt automatique du warehouse après 300 s d'inactivité (valeur optimisée)
    AUTO_RESUME = TRUE		-- Quand une nouvelle requête arrive sur un warehouse suspendu, il redémarre 	instantanément (< 2s de délai).
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Warehouse dédié MediCore ELT pipeline';

-- 2. Créer la Database et Schema RAW
CREATE OR REPLACE DATABASE MEDIcore
    COMMENT = 'Database MediCore - Pharmacie analytics';

CREATE OR REPLACE SCHEMA MEDIcore.RAW
    COMMENT = 'RAW layer - Données brutes depuis MySQL CDC';

CREATE OR REPLACE SCHEMA MEDIcore.STAGING
    COMMENT = 'STAGING layer - Données nettoyées/dédupliquées';

CREATE OR REPLACE SCHEMA MEDIcore.MARTS
    COMMENT = 'MART layer - Dimensions et faits analytiques';

-- 3. Créer rôles dédiés (RBAC)
CREATE OR REPLACE ROLE MEDIcore_RAW_WRITER
    COMMENT = 'Rôle pour écrire en RAW depuis Python/CDC loader';

CREATE OR REPLACE ROLE MEDIcore_DBT_EXECUTOR
    COMMENT = 'Rôle pour dbt : read RAW, write STAGING/MARTS';

CREATE OR REPLACE ROLE MEDIcore_ANALYST
    COMMENT = 'Rôle lecture MARTS pour analystes';

-- 4. Grants
GRANT USAGE ON WAREHOUSE MEDIcore_WH TO ROLE MEDIcore_RAW_WRITER;
GRANT USAGE ON WAREHOUSE MEDIcore_WH TO ROLE MEDIcore_DBT_EXECUTOR;
GRANT USAGE ON DATABASE MEDIcore TO ROLE MEDIcore_RAW_WRITER;
GRANT USAGE ON DATABASE MEDIcore TO ROLE MEDIcore_DBT_EXECUTOR;
GRANT USAGE ON DATABASE MEDIcore TO ROLE MEDIcore_ANALYST;

GRANT CREATE SCHEMA, USAGE ON SCHEMA MEDIcore.RAW TO ROLE MEDIcore_RAW_WRITER;
GRANT CREATE TABLE, USAGE ON SCHEMA MEDIcore.RAW TO ROLE MEDIcore_RAW_WRITER;
GRANT SELECT ON SCHEMA MEDIcore.RAW TO ROLE MEDIcore_DBT_EXECUTOR;

GRANT CREATE TABLE, USAGE ON SCHEMA MEDIcore.STAGING TO ROLE MEDIcore_DBT_EXECUTOR;
GRANT SELECT ON SCHEMA MEDIcore.STAGING TO ROLE MEDIcore_ANALYST;

GRANT CREATE TABLE, USAGE ON SCHEMA MEDIcore.MARTS TO ROLE MEDIcore_DBT_EXECUTOR;
GRANT SELECT ON SCHEMA MEDIcore.MARTS TO ROLE MEDIcore_ANALYST;

-- 5. Grant warehouse usage aux rôles
GRANT USAGE ON WAREHOUSE MEDIcore_WH TO ROLE MEDIcore_ANALYST;

-- 6. Associer rôles à un utilisateur (exemple : ton user dbt ou python)
-- GRANT ROLE MEDIcore_RAW_WRITER TO USER ton_user_python;
-- GRANT ROLE MEDIcore_DBT_EXECUTOR TO USER ton_user_dbt;
