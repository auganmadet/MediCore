{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID', 'FOU_ID'],
        schema='STAGING',
        tags=['staging', 'fournisseurs', 'ref', 'incremental']
    )
}}

with source_data as (
    select * from {{ source('mysql_raw', 'RAW_FOURNISSEURS') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, FOU_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, upper(trim(FOU_ID))       as FOU_ID,
    {{ pii_mask('FOU_NOM', 'FOU') }} as FOU_NOM,
    {{ pii_mask('FOU_ADRESSE', 'ADDR') }} as FOU_ADRESSE,
    trim(FOU_CP)              as FOU_CP,
    upper(trim(FOU_VILLE))    as FOU_VILLE,
    FOU_TYPE,
    FOU_REPARTITEUR,
    trim(FOU_ETABLISSEMENT)   as FOU_ETABLISSEMENT,
    trim(FOU_IDCLIENT)        as FOU_IDCLIENT,
    trim(FOU_URL1)            as FOU_URL1,
    trim(FOU_URL2)            as FOU_URL2,
    cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
