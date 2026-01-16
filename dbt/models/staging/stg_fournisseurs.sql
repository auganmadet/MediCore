{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PHA_ID', 'FOU_ID'],
        tags=['staging', 'fournisseurs', 'ref']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, FOU_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_fournisseurs') }}
    where cdc_operation != 'D'
)

select
    PHA_ID,
    upper(trim(FOU_ID))       as FOU_ID,
    upper(trim(FOU_NOM))      as FOU_NOM,
    trim(FOU_ADRESSE)         as FOU_ADRESSE,
    trim(FOU_CP)              as FOU_CP,
    upper(trim(FOU_VILLE))    as FOU_VILLE,
    FOU_TYPE,
    FOU_REPARTITEUR,
    trim(FOU_ETABLISSEMENT)   as FOU_ETABLISSEMENT,
    trim(FOU_IDCLIENT)        as FOU_IDCLIENT,
    trim(FOU_URL1)            as FOU_URL1,
    trim(FOU_URL2)            as FOU_URL2,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
