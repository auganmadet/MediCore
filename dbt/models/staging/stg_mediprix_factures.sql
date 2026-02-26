{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID', 'FAC_ID', 'FAC_TI'],
        schema='STAGING',
        tags=['staging', 'mediprix', 'high_volume', 'incremental']
    )
}}
{{ guard_full_refresh() }}

with source_data as (
    select * from {{ source('mysql_raw', 'RAW_MEDIPRIX_FACTURES') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
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
       {{ pii_mask('ORD_OPERATEUR', 'USER') }} as ORD_OPERATEUR,
       {{ pii_mask('PHA_NOM', 'PHARM') }} as PHA_NOM,
       cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
