

with source_data as (
    select * from MEDICORE.RAW.raw_pharmacies_erreur
    where cdc_operation != 'D'
    
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by id
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select id, code_erreur, date_erreur, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1