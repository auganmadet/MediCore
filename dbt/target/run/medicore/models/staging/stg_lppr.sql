
  
    

        create or replace transient table MEDICORE.STAGING.stg_lppr
         as
        (

with source_data as (
    select * from MEDICORE.RAW.raw_lppr
    where cdc_operation != 'D'
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, PRD_ID, LPP_INDEX, LPP_CODE
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, PRD_ID, LPP_INDEX, upper(trim(LPP_CODE)) as LPP_CODE,
       LPP_QTE, upper(trim(LPP_ACTE_NOM)) as LPP_ACTE_NOM,
       cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
        );
      
  