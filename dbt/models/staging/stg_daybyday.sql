{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PHA_ID', 'DBD_DATE', 'PRD_ID'],
        tags=['staging', 'daybyday']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, DBD_DATE, PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_daybyday') }}
    where cdc_operation != 'D'
)

select
    PHA_ID,
    DBD_DATE,
    PRD_ID,
    DBD_PRIXTARIF,
    DBD_PRIXPUBLIC,
    DBD_PAMP,
    DBD_PANET,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
