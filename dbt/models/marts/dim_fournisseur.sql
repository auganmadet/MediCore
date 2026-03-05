{{
  config(
    materialized='table',
    schema='MARTS',
    tags=['marts', 'dim', 'fournisseur']
  )
}}

with fournisseurs_dedup as (
    select
        PHA_ID,
        FOU_ID,
        FOU_NOM,
        FOU_ADRESSE,
        FOU_CP,
        FOU_VILLE,
        FOU_TYPE,
        FOU_REPARTITEUR,
        FOU_ETABLISSEMENT,
        FOU_IDCLIENT,
        FOU_URL1,
        FOU_URL2,
        row_number() over (
          partition by PHA_ID, FOU_ID
          order by loaded_at desc
        ) as rn
    from {{ ref('stg_fournisseurs') }}
)

select
    md5(PHA_ID::string || '-' || FOU_ID::string) as fournisseur_sk,
    PHA_ID,
    FOU_ID,
    FOU_NOM,
    FOU_ADRESSE,
    FOU_CP,
    FOU_VILLE,
    FOU_TYPE,
    FOU_REPARTITEUR,
    FOU_ETABLISSEMENT,
    FOU_IDCLIENT,
    FOU_URL1,
    FOU_URL2
from fournisseurs_dedup
where rn = 1

union all

select
    md5('-1' || '-' || '-1') as fournisseur_sk,
    -1 as PHA_ID, '-1' as FOU_ID,
    'INCONNU' as FOU_NOM,
    null as FOU_ADRESSE, null as FOU_CP, null as FOU_VILLE,
    null as FOU_TYPE, null as FOU_REPARTITEUR, null as FOU_ETABLISSEMENT,
    null as FOU_IDCLIENT, null as FOU_URL1, null as FOU_URL2
