

with source_data as (
    select * from MEDICORE.RAW.raw_produits
    where cdc_operation != 'D'
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, PRD_ID, trim(PRD_EAN13) as PRD_EAN13, upper(trim(PRD_NOM)) as PRD_NOM,
    PRD_IDMAJPRD, upper(trim(FOU_ID)) as FOU_ID, PRD_CODEREMBT,
    trim(PRD_CODEACTE) as PRD_CODEACTE, PRD_FIRSTSTOCK, PRD_TVA, PRD_NTVA,
    PRD_CREATE, PRD_STOCK, PRD_PRIXTARIF, PRD_DERN_VENTE, PRD_DERN_ACHAT,
    PRD_FLAG3, PRD_REFGEN, PRD_EN_STOCK, PRD_EN_COMMANDE, PRD_EN_PROMIS,
    PRD_DELETED, PRD_ONLYPROMIS, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1