{{
  config(
    materialized='view',
    schema='AUDIT',
    tags=['audit']
  )
}}

-- 7 derniers jours : détail step par step
WITH recent_runs AS (
    SELECT RUN_ID, RUN_START, RUN_END, STATUS AS run_status, ENV
    FROM {{ target.database }}.AUDIT.PIPELINE_RUNS
    WHERE RUN_START >= DATEADD('day', -7, CURRENT_TIMESTAMP())
)

SELECT
    r.RUN_ID,
    r.RUN_START,
    r.RUN_END,
    r.run_status,
    r.ENV,
    s.STEP_NAME,
    s.STEP_START,
    s.STEP_END,
    s.STATUS AS step_status,
    s.ROWS_PROCESSED AS ROWS_AFFECTED,
    s.ERROR_MESSAGE,
    TIMESTAMPDIFF('second', s.STEP_START, COALESCE(s.STEP_END, CURRENT_TIMESTAMP())) AS step_duration_seconds
FROM recent_runs r
LEFT JOIN {{ target.database }}.AUDIT.PIPELINE_STEP_RUNS s ON r.RUN_ID = s.RUN_ID
ORDER BY r.RUN_START DESC, s.STEP_START ASC
