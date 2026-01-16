{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PRD_ID'],
        tags=['staging', 'produits_negatifs']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_produits_negatifs') }}
    where cdc_operation != 'D'
)

select
    PRD_ID,
    upper(trim(PRD_NOM)) as PRD_NOM,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
