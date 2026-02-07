-- {{
--     config(
--         schema='RAW',
--         tags=['raw', 'prix_journalier']
--     )
-- }}

-- select * from {{ source('mysql_raw', 'RAW_DAYBYDAY') }}


{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['PHA_ID', 'DBD_DATE', 'PRD_ID'],
    schema='RAW',
    tags=['cdc', 'daybyday']
) }}

WITH cdc_raw AS (
  SELECT 
    payload.after.PHA_ID,
    payload.after.DBD_DATE,
    payload.after.PRD_ID,
    payload.after.DBD_PRIXTARIF,
    payload.after.DBD_PRIXPUBLIC,
    payload.after.DBD_PAMP,
    payload.after.DBD_PANET,
    payload.source.ts_ms AS cdc_timestamp,
    payload.source.file AS cdc_file,
    payload.source.pos AS cdc_pos,
    payload.op AS cdc_op
  FROM {{ source('kafka_cdc', 'winstat_daybyday') }}
  WHERE payload.op IN ('c', 'u', 'd') 
    AND payload.after IS NOT NULL
)
SELECT * FROM cdc_raw
{% if is_incremental() %}
  WHERE cdc_timestamp > (SELECT MAX(cdc_timestamp) FROM {{ this }})
{% endif %}

