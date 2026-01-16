{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['id'],
        tags=['staging', 'pharmacies_ref']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by id
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_pharmacies') }}
    where cdc_operation != 'D'
)

select
    id,
    upper(trim(adeli))       as adeli,
    upper(trim(name))        as name,
    trim(phone)              as phone,
    upper(trim(city))        as city,
    upper(trim(postal_code)) as postal_code,
    parent_id,
    left_groupment,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
