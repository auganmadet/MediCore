{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID'],
        schema='STAGING',
        tags=['staging', 'pharmacie', 'ref', 'incremental']
    )
}}

with source_data as (
    select * from {{ source('mysql_raw', 'RAW_PHARMACIE') }}
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
select PHA_ID, upper(trim(PHA_IDNAT)) as PHA_IDNAT, upper(trim(PHA_GERS)) as PHA_GERS,
    {{ pii_mask('PHA_NOM', 'PHARM') }} as PHA_NOM, PHA_DATE_INSTAL_WP, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
