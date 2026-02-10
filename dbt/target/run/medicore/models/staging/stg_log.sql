
  
    

        create or replace transient table MEDICORE.STAGING.stg_log
         as
        (

with source_data as (
    select * from MEDICORE.RAW.raw_log
    where cdc_operation != 'D'
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, DATE_SYNC, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
        );
      
  