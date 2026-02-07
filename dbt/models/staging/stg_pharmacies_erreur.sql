{{
    config(
        materialized='table',
        incremental_strategy='merge',
        unique_key=['id'],
        schema='STAGING',
        tags=['staging', 'pharmacies_erreur', 'audit', 'incremental']
    )
}}

with source_data as (
    select * from {{ ref('raw_pharmacies_erreur') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select id, code_erreur, date_erreur, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
