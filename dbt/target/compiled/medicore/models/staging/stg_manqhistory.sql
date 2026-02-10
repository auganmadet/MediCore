

with source_data as (
    select * from MEDICORE.RAW.raw_manqhistory
    where cdc_operation != 'D'
    
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from MEDICORE.STAGING.stg_manqhistory)
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, MNQ_DATE, PRD_ID, FAC_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, MNQ_DATE, PRD_ID, FAC_ID, EN_LIGNES, EN_BOITES,
       EN_CLIENTS, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1