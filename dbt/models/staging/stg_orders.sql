-- {{
--     config(
--         materialized='table',
--         schema='STAGING',
--         unique_key=['PHA_ID', 'FAC_ID'],
--         tags=['staging', 'orders', 'high_volume']
--     )
-- }}

-- with dedup_cdc as (
--     select *,
--         row_number() over (
--             partition by PHA_ID, FAC_ID
--             order by cdc_timestamp desc nulls last
--         ) as rn
--     from {{ ref('raw_orders') }}
--     where cdc_operation != 'D'
-- )

-- select
--     PHA_ID,
--     FAC_ID,
--     ORD_DATE,
--     upper(trim(ORD_OPERATEUR)) as ORD_OPERATEUR,
--     ORD_CLIENT_AGE_MONTHS,
--     upper(trim(ORD_CLIENT_SEX)) as ORD_CLIENT_SEX,
--     upper(trim(ORD_CLIENT_DEPARTMENT)) as ORD_CLIENT_DEPARTMENT,
--     ORD_HISTO_NBCLIENT,
--     ORD_BASE,
--     ORD_RETRO,
--     ORD_LOCATION,
--     ORD_ORDO,
--     ORD_AVR,
--     ORD_ANN,
--     ORD_DATE_ORDON,
--     ORD_DATE_ORDER,
--     upper(trim(ORD_CODE_SUBRO)) as ORD_CODE_SUBRO,
--     ORD_TOTAL_GENERAL,
--     ORD_TOTAL_REMB_SS,
--     ORD_TOTAL_REMB_MUTU,
--     ORD_CLI_TI,
--     ORD_BEN_TI,
--     ORD_MED_TI,
--     ORD_MED_SPEC,
--     ORD_OPER_CODE,
--     ORD_CLI_TYPE,
--     cdc_timestamp as loaded_at
-- from dedup_cdc
-- where rn = 1


{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID', 'FAC_ID'],
        schema='STAGING',
        tags=['staging', 'orders', 'high_volume', 'incremental']
    )
}}

with source_data as (
    select * from {{ ref('raw_orders') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, FAC_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, FAC_ID, ORD_DATE, upper(trim(ORD_OPERATEUR)) as ORD_OPERATEUR,
       ORD_CLIENT_AGE_MONTHS, upper(trim(ORD_CLIENT_SEX)) as ORD_CLIENT_SEX,
       upper(trim(ORD_CLIENT_DEPARTMENT)) as ORD_CLIENT_DEPARTMENT,
       ORD_HISTO_NBCLIENT, ORD_BASE, ORD_RETRO, ORD_LOCATION, ORD_ORDO,
       ORD_AVR, ORD_ANN, ORD_DATE_ORDON, ORD_DATE_ORDER,
       upper(trim(ORD_CODE_SUBRO)) as ORD_CODE_SUBRO, ORD_TOTAL_GENERAL,
       ORD_TOTAL_REMB_SS, ORD_TOTAL_REMB_MUTU, ORD_CLI_TI, ORD_BEN_TI,
       ORD_MED_TI, ORD_MED_SPEC, ORD_OPER_CODE, ORD_CLI_TYPE,
       cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
