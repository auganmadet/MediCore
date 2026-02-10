

with source_data as (
    select *
    from MEDICORE.RAW.RAW_COMMANDES
    where cdc_operation != 'D'
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, COM_GROI, PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select 
    PHA_ID, COM_GROI, PRD_ID, COM_GROS, COM_DATE,
    upper(trim(FOU_ID)) as FOU_ID,
    COM_QUANTITE, COM_PAHTNET, COM_TAUXREMISE,
    cdc_timestamp as loaded_at
from dedup_cdc 
where rn = 1