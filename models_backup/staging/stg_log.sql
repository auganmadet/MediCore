-- {{
--     config(
--         schema='STAGING',
--         unique_key=['PHA_ID'],
--         tags=['staging', 'log', 'audit']
--     )
-- }}

-- with dedup_cdc as (
--     select *,
--         row_number() over (
--             partition by PHA_ID
--             order by cdc_timestamp desc nulls last
--         ) as rn
--     from {{ ref('raw_log') }}
--     where cdc_operation != 'D'
-- )

-- select
--     PHA_ID,
--     DATE_SYNC,
--     cdc_timestamp as loaded_at
-- from dedup_cdc
-- where rn = 1


{{
    config(
        materialized='table',
        incremental_strategy='merge',
        unique_key=['PHA_ID'],
        schema='STAGING',
        tags=['staging', 'log', 'incremental']
    )
}}

with source_data as (
    select * from {{ ref('raw_log') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, DATE_SYNC, cdc_timestamp as loaded_at
from dedup_cdc where rn = 1

