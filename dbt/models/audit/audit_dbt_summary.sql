{{
  config(
    materialized='view',
    schema='AUDIT',
    tags=['audit']
  )
}}

-- Résumé dbt par invocation : models ok/warn/error, temps total
SELECT
    RUN_ID,
    DBT_INVOCATION_ID,
    COUNT(*) AS total_models,
    SUM(CASE WHEN STATUS IN ('pass', 'success') THEN 1 ELSE 0 END) AS models_ok,
    SUM(CASE WHEN STATUS = 'warn' THEN 1 ELSE 0 END) AS models_warn,
    SUM(CASE WHEN STATUS IN ('error', 'fail') THEN 1 ELSE 0 END) AS models_error,
    SUM(CASE WHEN STATUS = 'skip' THEN 1 ELSE 0 END) AS models_skip,
    SUM(EXECUTION_TIME_S) AS total_execution_time_s,
    SUM(ROWS_AFFECTED) AS total_rows_affected,
    MIN(CREATED_AT) AS first_model_at,
    MAX(CREATED_AT) AS last_model_at
FROM MEDICORE.AUDIT.DBT_MODEL_RUNS
GROUP BY RUN_ID, DBT_INVOCATION_ID
