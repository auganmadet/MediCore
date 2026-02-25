{{
  config(
    materialized='view',
    schema='AUDIT',
    tags=['audit']
  )
}}

-- Résumé par run : durée, steps ok/failed, rows total
WITH runs AS (
    SELECT
        RUN_ID,
        RUN_START,
        RUN_END,
        STATUS,
        ENV,
        TRIGGERED_BY,
        TIMESTAMPDIFF('second', RUN_START, COALESCE(RUN_END, CURRENT_TIMESTAMP())) AS duration_seconds
    FROM MEDICORE.AUDIT.PIPELINE_RUNS
),

steps_agg AS (
    SELECT
        RUN_ID,
        COUNT(*) AS total_steps,
        SUM(CASE WHEN STATUS = 'SUCCESS' THEN 1 ELSE 0 END) AS steps_ok,
        SUM(CASE WHEN STATUS = 'FAILED' THEN 1 ELSE 0 END) AS steps_failed,
        SUM(COALESCE(ROWS_AFFECTED, 0)) AS total_rows
    FROM MEDICORE.AUDIT.PIPELINE_STEP_RUNS
    GROUP BY RUN_ID
)

SELECT
    r.RUN_ID,
    r.RUN_START,
    r.RUN_END,
    r.STATUS,
    r.ENV,
    r.TRIGGERED_BY,
    r.duration_seconds,
    COALESCE(s.total_steps, 0) AS total_steps,
    COALESCE(s.steps_ok, 0) AS steps_ok,
    COALESCE(s.steps_failed, 0) AS steps_failed,
    COALESCE(s.total_rows, 0) AS total_rows
FROM runs r
LEFT JOIN steps_agg s ON r.RUN_ID = s.RUN_ID
