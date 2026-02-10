{{ 
  config(
    materialized='table',
    schema='MARTS',
    tags=['marts', 'fact', 'stock_mouvement']
  ) 
}}

with mouvements as (
    select
        m.PHA_ID,
        m.PRD_ID,
        m.MOD_DATE::date as date_mouvement,
        m.MOD_DELTA      as delta_stock,
        m.MOD_STOCK      as stock_apres,
        m.MOD_OPERATION,
        ph.pharmacie_sk,
        prod.produit_sk,
        row_number() over (
          partition by m.PHA_ID, m.PRD_ID, m.MOD_DATE, m.MOD_TIMESTAMP
          order by m.loaded_at desc
        ) as rn
    from {{ ref('stg_modstock') }} m
    left join {{ ref('dim_pharmacie') }} ph
      on m.PHA_ID = ph.PHA_ID
      and m.MOD_DATE between ph.valid_from and ph.valid_to
    left join {{ ref('dim_produit') }} prod
      on m.PHA_ID = prod.PHA_ID
      and m.PRD_ID = prod.PRD_ID
)

select
    pharmacie_sk,
    produit_sk,
    date_mouvement,
    sum(delta_stock) as delta_stock,
    max(stock_apres) as stock_apres,
    max(MOD_OPERATION) as type_operation
from mouvements
where rn = 1
group by 1,2,3
