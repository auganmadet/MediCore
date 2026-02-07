-- {{
--     config(
--         schema='STAGING',
--         unique_key=['PHA_ID', 'EAN_13', 'PRD_ID'],
--         tags=['staging', 'ean13']
--     )
-- }}

-- with dedup_cdc as (
--     select *,
--         row_number() over (
--             partition by PHA_ID, EAN_13, PRD_ID
--             order by cdc_timestamp desc nulls last
--         ) as rn
--     from {{ ref('raw_ean13') }}
--     where cdc_operation != 'D'
-- )

-- select
--     PHA_ID,
--     upper(trim(EAN_13)) as EAN_13,
--     PRD_ID,
--     cdc_timestamp as loaded_at
-- from dedup_cdc
-- where rn = 1


{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID', 'EAN_13', 'PRD_ID'],
        schema='STAGING',
        tags=['staging', 'ean13', 'incremental']
    )
}}

with source_data as (
    select * from {{ ref('raw_ean13') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, EAN_13, PRD_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, upper(trim(EAN_13)) as EAN_13, PRD_ID, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1

