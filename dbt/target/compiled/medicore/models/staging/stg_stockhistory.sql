

with source_data as (
    select * from MEDICORE.RAW.raw_stockhistory
    where cdc_operation != 'D'
    
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from MEDICORE.STAGING.stg_stockhistory)
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, PRD_ID, STH_DATE
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, PRD_ID, STH_DATE, STH_STOCKDELTA, STH_STOCK,
       STH_PRIXTARIF, STH_PRIXPUBLIC, STH_PAMP, STH_PANET,
       cdc_timestamp as loaded_at
from dedup_cdc where rn = 1