{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['id'],
        tags=['staging', 'pharmacies_erreur', 'audit']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by id
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_pharmacies_erreur') }}
    where cdc_operation != 'D'
)

select
    id,
    code_erreur,
    date_erreur,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
