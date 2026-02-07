{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID', 'COM_GROI', 'PRD_ID'],
        schema='STAGING',
        tags=['staging', 'commandes', 'incremental']
    )
}}

with source_data as (
    select *
    from {{ source('mysql_raw', 'RAW_COMMANDES') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, COM_GROI, PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select 
    PHA_ID, COM_GROI, PRD_ID, COM_GROS, COM_DATE,
    upper(trim(FOU_ID)) as FOU_ID,
    COM_QUANTITE, COM_PAHTNET, COM_TAUXREMISE,
    cdc_timestamp as loaded_at
from dedup_cdc where rn = 1



