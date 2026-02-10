

with source_data as (
    select * from MEDICORE.RAW.raw_mediprix_factures
    where cdc_operation != 'D'
    
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from MEDICORE.STAGING.stg_mediprix_factures)
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, FAC_ID, FAC_TI
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select id, PHA_ID, FAC_ID, FAC_TI, FAC_DATE, FAC_HEURE, FAC_TVA,
       FAC_QUANTITE, FAC_PAHT, FAC_PVHT, FAC_PVTTC, FAC_PRIXPUBLIC,
       FAC_CODEREMBT, PRD_ID, PRD_EAN13, upper(trim(PRD_NOM)) as PRD_NOM,
       upper(trim(ORD_OPERATEUR)) as ORD_OPERATEUR, upper(trim(PHA_NOM)) as PHA_NOM,
       cdc_timestamp as loaded_at
from dedup_cdc where rn = 1