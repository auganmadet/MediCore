-- {{
--     config(
--         materialized='table',
--         schema='STAGING',
--         unique_key=['PRD_ID'],
--         tags=['staging', 'produits_negatifs']
--     )
-- }}

-- with dedup_cdc as (
--     select *,
--         row_number() over (
--             partition by PRD_ID
--             order by cdc_timestamp desc nulls last
--         ) as rn
--     from {{ ref('raw_produits_negatifs') }}
--     where cdc_operation != 'D'
-- )

-- select
--     PRD_ID,
--     upper(trim(PRD_NOM)) as PRD_NOM,
--     cdc_timestamp as loaded_at
-- from dedup_cdc
-- where rn = 1


{{
    config(
        materialized='table',
        incremental_strategy='merge',
        unique_key=['PRD_ID'],
        schema='STAGING',
        tags=['staging', 'produits_negatifs', 'ref', 'incremental']
    )
}}

with source_data as (
    select * from {{ ref('raw_produits_negatifs') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
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