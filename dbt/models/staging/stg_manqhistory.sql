{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PHA_ID', 'MNQ_DATE', 'PRD_ID', 'FAC_ID'],
        tags=['staging', 'manqhistory']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, MNQ_DATE, PRD_ID, FAC_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_manqhistory') }}
    where cdc_operation != 'D'
)

select
    PHA_ID,
    MNQ_DATE,
    PRD_ID,
    FAC_ID,
    EN_LIGNES,
    EN_BOITES,
    EN_CLIENTS,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
