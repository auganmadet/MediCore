{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PHA_ID', 'EAN_13', 'PRD_ID'],
        tags=['staging', 'ean13']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, EAN_13, PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_ean13') }}
    where cdc_operation != 'D'
)

select
    PHA_ID,
    upper(trim(EAN_13)) as EAN_13,
    PRD_ID,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
