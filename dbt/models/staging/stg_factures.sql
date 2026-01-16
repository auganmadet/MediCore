{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PHA_ID', 'FAC_ID', 'FAC_TI'],
        tags=['staging', 'factures', 'high_volume']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, FAC_ID, FAC_TI
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_factures') }}
    where cdc_operation != 'D'
)

select
    PHA_ID,
    FAC_ID,
    FAC_TI,
    FAC_BASE,
    FAC_DATE,
    PRD_ID,
    FAC_TVA,
    FAC_QUANTITE,
    FAC_PAHT,
    FAC_PVHT,
    FAC_PVTTC,
    FAC_PRIXPUBLIC,
    FAC_REMISE,
    FAC_CODEREMBT,
    FAC_HISTO_NBCLIENT,
    FAC_PROMO,
    FAC_RETRO,
    FAC_LOCATION,
    FAC_ORDO,
    cdc_timestamp as loaded_at
from dedup_cdc
where rn = 1
