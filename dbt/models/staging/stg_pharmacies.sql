{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['id'],
        schema='STAGING',
        tags=['staging', 'pharmacies_ref', 'incremental']
    )
}}

with source_data as (
    select * from {{ source('mysql_raw', 'RAW_PHARMACIES') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by id
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select id,
    '***' || RIGHT(CAST(adeli AS VARCHAR), 4) as adeli,
    'PHARM_' || LEFT(MD5(CAST(name AS VARCHAR)), 4) as name,
    LEFT(REPLACE(REPLACE(CAST(phone AS VARCHAR), ' ', ''), '.', ''), 2) || '**' || RIGHT(REPLACE(REPLACE(CAST(phone AS VARCHAR), ' ', ''), '.', ''), 4) as phone,
    upper(trim(city)) as city,
    LEFT(CAST(postal_code AS VARCHAR), 2) || '***' as postal_code,
    parent_id, left_groupment, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
