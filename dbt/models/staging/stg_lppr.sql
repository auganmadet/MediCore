{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID', 'PRD_ID', 'LPP_INDEX', 'LPP_CODE'],
        schema='STAGING',
        tags=['staging', 'lppr', 'ref', 'incremental']
    )
}}

with source_data as (
    select * from {{ source('mysql_raw', 'RAW_LPPR') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, PRD_ID, LPP_INDEX, LPP_CODE
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, PRD_ID, LPP_INDEX, upper(trim(LPP_CODE)) as LPP_CODE,
       LPP_QTE, upper(trim(LPP_ACTE_NOM)) as LPP_ACTE_NOM,
       cdc_timestamp as loaded_at
from dedup_cdc where rn = 1