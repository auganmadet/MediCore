

with source_data as (
    select * from MEDICORE.RAW.raw_ean13
    where cdc_operation != 'D'
    
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from MEDICORE.STAGING.stg_ean13)
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, EAN_13, PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, upper(trim(EAN_13)) as EAN_13, PRD_ID, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1