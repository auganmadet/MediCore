{{
    config(
        materialized='table',
        schema='STAGING',
        tags=['staging', 'pharmacie', 'ref']
    )
}}

with source_data as (
    select * from {{ ref('raw_pharmacie') }}
    where cdc_operation != 'D'
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, upper(trim(PHA_IDNAT)) as PHA_IDNAT, upper(trim(PHA_GERS)) as PHA_GERS,
    upper(trim(PHA_NOM)) as PHA_NOM, PHA_DATE_INSTAL_WP, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
