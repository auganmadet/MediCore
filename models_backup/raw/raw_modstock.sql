-- {{
--     config(
--         schema='RAW',
--         tags=['raw', 'stock_mouvements']
--     )
-- }}

-- select * from {{ source('mysql_raw', 'RAW_MODSTOCK') }}


{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['PHA_ID', 'MOD_DATE', 'PRD_ID'],
    schema='RAW',
    tags=['cdc', 'modstock']
) }}

WITH cdc_raw AS (
  SELECT 
    payload.after.PHA_ID,
    payload.after.MOD_DATE,
    payload.after.PRD_ID,
    payload.after.MOD_TIMESTAMP,
    payload.after.MOD_DELTA,
    payload.after.MOD_TI,
    payload.after.MOD_STOCK,
    payload.after.MOD_FACTURE,
    payload.after.MOD_COMMANDE,
    payload.after.MOD_OPERATION,
    payload.after.MOD_PARAM2,
    payload.after.MOD_POSTE,
    payload.after.MOD_DELTA_RESERVE,
    payload.after.MOD_CODE_ZONE,
    payload.source.ts_ms AS cdc_timestamp,
    payload.source.file AS cdc_file,
    payload.source.pos AS cdc_pos,
    payload.op AS cdc_op
  FROM {{ source('kafka_cdc', 'winstat_modstock') }}
  WHERE payload.op IN ('c', 'u', 'd') 
    AND payload.after IS NOT NULL
)
SELECT * FROM cdc_raw
{% if is_incremental() %}
  WHERE cdc_timestamp > (SELECT MAX(cdc_timestamp) FROM {{ this }})
{% endif %}

