
  create or replace   view MEDICORE.STAGING.stg_modstock
  
   as (
    

with source_data as (
    select * from MEDICORE.RAW.raw_modstock
    where cdc_operation != 'D'
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, MOD_DATE, PRD_ID, MOD_TIMESTAMP
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, MOD_DATE, PRD_ID, MOD_TIMESTAMP, MOD_DELTA, MOD_TI,
       MOD_STOCK, MOD_FACTURE, MOD_COMMANDE, MOD_OPERATION, MOD_PARAM2,
       upper(trim(MOD_POSTE)) as MOD_POSTE, MOD_DELTA_RESERVE, MOD_CODE_ZONE,
       cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
  );

