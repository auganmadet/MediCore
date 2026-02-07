-- {{
--     config(
--         schema='RAW',
--         tags=['raw', 'dim_pharmacie']
--     )
-- }}

-- select * from {{ source('mysql_raw', 'RAW_PHARMACIE') }}


{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['PHA_ID'],
    schema='RAW',
    tags=['cdc', 'pharmacie']
) }}

WITH cdc_raw AS (
  SELECT 
    payload.after.PHA_ID,
    payload.after.PHA_IDNAT,
    payload.after.PHA_GERS,
    payload.after.PHA_NOM,
    payload.after.PHA_DATE_INSTAL_WP,
    payload.source.ts_ms AS cdc_timestamp,
    payload.source.file AS cdc_file,
    payload.source.pos AS cdc_pos,
    payload.op AS cdc_op
  FROM {{ source('kafka_cdc', 'winstat_pharmacie') }}
  WHERE payload.op IN ('c', 'u', 'd') 
    AND payload.after IS NOT NULL
)
SELECT * FROM cdc_raw
{% if is_incremental() %}
  WHERE cdc_timestamp > (SELECT MAX(cdc_timestamp) FROM {{ this }})
{% endif %}

