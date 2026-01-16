{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PHA_ID', 'PRD_ID', 'STH_DATE'],
        tags=['staging', 'stockhistory']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, PRD_ID, STH_DATE
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_stockhistory') }}
    where cdc_operation != 'D'
)

select
    PHA_ID,
    PRD_ID,
    STH_DATE,
    STH_STOCKDELTA,
    STH_STOCK,
    STH_PRIXTARIF,
    STH_PRIXPUBLIC,
    STH_PAMP,
    STH_PANET,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
