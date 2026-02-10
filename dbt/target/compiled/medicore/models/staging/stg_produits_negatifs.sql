

with source_data as (
    select * from MEDICORE.RAW.raw_produits_negatifs
    where cdc_operation != 'D'
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PRD_ID, upper(trim(PRD_NOM)) as PRD_NOM, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1