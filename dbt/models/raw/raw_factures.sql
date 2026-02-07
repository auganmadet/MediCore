{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['PHA_ID', 'FAC_ID', 'FAC_TI'],
    schema='RAW',
    tags=['cdc', 'factures']
) }}

WITH cdc_raw AS (
  SELECT 
    payload.after.PHA_ID,
    payload.after.FAC_ID,
    payload.after.FAC_TI,
    payload.after.FAC_BASE,
    payload.after.FAC_DATE,
    payload.after.PRD_ID,
    payload.after.FAC_TVA,
    payload.after.FAC_QUANTITE,
    payload.after.FAC_PAHT,
    payload.after.FAC_PVHT,
    payload.after.FAC_PVTTC,
    payload.after.FAC_PRIXPUBLIC,
    payload.after.FAC_REMISE,
    payload.after.FAC_CODEREMBT,
    payload.after.FAC_HISTO_NBCLIENT,
    payload.after.FAC_PROMO,
    payload.after.FAC_RETRO,
    payload.after.FAC_LOCATION,
    payload.after.FAC_ORDO,
    payload.source.ts_ms AS cdc_timestamp,
    payload.source.file AS cdc_file,
    payload.source.pos AS cdc_pos,
    payload.op AS cdc_op
  FROM {{ source('kafka_cdc', 'winstat_factures') }}
  WHERE payload.op IN ('c', 'u', 'd') 
    AND payload.after IS NOT NULL
)
SELECT * FROM cdc_raw
{% if is_incremental() %}
  WHERE cdc_timestamp > (SELECT MAX(cdc_timestamp) FROM {{ this }})
{% endif %}
