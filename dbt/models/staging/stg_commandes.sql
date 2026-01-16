{{
    config(
        materialized='table',
        schema='STAGING',
        unique_key=['PHA_ID', 'COM_GROI', 'PRD_ID'],
        tags=['staging', 'commandes']
    )
}}

with dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, COM_GROI, PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from {{ ref('raw_commandes') }}
    where cdc_operation != 'D'
)
select 
    PHA_ID,
    COM_GROI,
    PRD_ID,
    COM_GROS,
    COM_DATE,
    upper(trim(FOU_ID)) as FOU_ID,
    COM_QUANTITE,
    COM_PAHTNET,
    COM_TAUXREMISE,
    cdc_timestamp as loaded_at
from dedup_cdc 
where rn = 1
