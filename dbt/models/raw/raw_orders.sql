{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['PHA_ID', 'FAC_ID'],
    schema='RAW',
    tags=['cdc', 'orders']
) }}

WITH cdc_raw AS (
  SELECT 
    payload.after.PHA_ID,
    payload.after.FAC_ID,
    payload.after.ORD_DATE,
    payload.after.ORD_OPERATEUR,
    payload.after.ORD_CLIENT_AGE_MONTHS,
    payload.after.ORD_CLIENT_SEX,
    payload.after.ORD_CLIENT_DEPARTEMENT,
    payload.after.ORD_HISTO_NBCLIENT,
    payload.after.ORD_BASE,
    payload.after.ORD_RETRO,
    payload.after.ORD_LOCATION,
    payload.after.ORD_ORDO,
    payload.after.ORD_AVR,
    payload.after.ORD_ANN,
    payload.after.ORD_DATE_ORDON,
    payload.after.ORD_DATE_ORDER,
    payload.after.ORD_CODE_SUBRO,
    payload.after.ORD_TOTAL_GENERAL,
    payload.after.ORD_TOTAL_REMB_SS,
    payload.after.ORD_TOTAL_REMB_MUTU,
    payload.after.ORD_CLI_TI,
    payload.after.ORD_BEN_TI,
    payload.after.ORD_MED_TI,
    payload.after.ORD_MED_SPEC,
    payload.after.ORD_OPER_CODE,
    payload.after.ORD_CLI_TYPE,
    payload.source.ts_ms AS cdc_timestamp,
    payload.source.file AS cdc_file,
    payload.source.pos AS cdc_pos,
    payload.op AS cdc_op
  FROM {{ source('kafka_cdc', 'winstat_orders') }}
  WHERE payload.op IN ('c', 'u', 'd') 
    AND payload.after IS NOT NULL
)
SELECT * FROM cdc_raw
{% if is_incremental() %}
  WHERE cdc_timestamp > (SELECT MAX(cdc_timestamp) FROM {{ this }})
{% endif %}
