{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PHA_ID'],
        tags=['staging', 'log', 'audit']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_log') }}
    where cdc_operation != 'D'
)

select
    PHA_ID,
    DATE_SYNC,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
