{{
  config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['pharmacie_sk', 'produit_sk', 'date_mouvement'],
    schema='MARTS',
    tags=['marts', 'fact', 'stock_mouvement', 'high_volume', 'incremental']
  )
}}
{{ guard_full_refresh() }}

with mouvements as (
    select
        m.PHA_ID,
        m.PRD_ID,
        m.MOD_DATE::date as date_mouvement,
        m.MOD_DELTA      as delta_stock,
        m.MOD_STOCK      as stock_apres,
        m.MOD_OPERATION,
        coalesce(ph.pharmacie_sk, md5('-1')) as pharmacie_sk,
        coalesce(prod.produit_sk, md5('-1' || '-' || '-1')) as produit_sk,
        m.loaded_at,
        row_number() over (
          partition by m.PHA_ID, m.PRD_ID, m.MOD_DATE, m.MOD_TIMESTAMP
          order by m.loaded_at desc
        ) as rn
    from {{ ref('stg_modstock') }} m
    left join {{ ref('dim_pharmacie') }} ph
      on m.PHA_ID = ph.PHA_ID
    left join {{ ref('dim_produit') }} prod
      on m.PHA_ID = prod.PHA_ID
      and m.PRD_ID = prod.PRD_ID
    {% if is_incremental() %}
    where m.loaded_at >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
)

select
    pharmacie_sk,
    produit_sk,
    date_mouvement,
    sum(delta_stock) as delta_stock,
    max(stock_apres) as stock_apres,
    max(MOD_OPERATION) as type_operation,
    max(loaded_at) as loaded_at
from mouvements
where rn = 1
group by pharmacie_sk, produit_sk, date_mouvement
