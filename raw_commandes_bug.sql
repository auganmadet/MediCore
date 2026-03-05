{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['PHA_ID', 'COM_GROI', 'PRD_ID'],
    schema='RAW',
    tags=['cdc', 'commandes']
) }}

WITH cdc_raw AS (
  SELECT 
    payload.after.PHA_ID,
    payload.after.COM_GROI,
    payload.after.PRD_ID,
    payload.after.COM_GROS,
    payload.after.COM_DATE,
    payload.after.FOU_ID,
    payload.after.COM_QUANTITE,
    payload.after.COM_PAHTNET,
    payload.after.COM_TAUXREMISE,
    payload.source.ts_ms AS cdc_timestamp,
    payload.source.file AS cdc_file,
    payload.source.pos AS cdc_pos,
    payload.op AS cdc_op
  FROM {{ source('kafka_cdc', 'winstat_commandes') }}
  WHERE payload.op IN ('c', 'u', 'd') 
    AND payload.after IS NOT NULL
)
SELECT * FROM cdc_raw
{% if is_incremental() %}
  WHERE cdc_timestamp > (SELECT MAX(cdc_timestamp) FROM {{ this }})
{% endif %}
