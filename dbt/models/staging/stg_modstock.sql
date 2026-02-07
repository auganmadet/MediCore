{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID', 'MOD_DATE', 'PRD_ID', 'MOD_TIMESTAMP'],
        schema='STAGING',
        tags=['staging', 'modstock', 'high_volume', 'incremental']
    )
}}

with source_data as (
    select * from {{ ref('raw_modstock') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, MOD_DATE, PRD_ID, MOD_TIMESTAMP
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, MOD_DATE, PRD_ID, MOD_TIMESTAMP, MOD_DELTA, MOD_TI,
       MOD_STOCK, MOD_FACTURE, MOD_COMMANDE, MOD_OPERATION, MOD_PARAM2,
       upper(trim(MOD_POSTE)) as MOD_POSTE, MOD_DELTA_RESERVE, MOD_CODE_ZONE,
       cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
