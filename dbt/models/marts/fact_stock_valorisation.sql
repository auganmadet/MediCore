{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['pharmacie_sk', 'produit_sk', 'date_stock'],
        schema='MARTS',
        tags=['marts', 'fact', 'stock_valorisation', 'high_volume', 'incremental']
    )
}}
{{ guard_full_refresh() }}

with stock_enriched as (
    select
        s.PHA_ID,
        s.PRD_ID,
        s.STH_DATE::date                as date_stock,
        s.STH_STOCK,
        s.STH_STOCKDELTA,
        s.STH_PRIXTARIF,
        s.STH_PRIXPUBLIC,
        s.STH_PAMP,
        s.STH_PANET,
        coalesce(ph.pharmacie_sk, md5('-1')) as pharmacie_sk,
        coalesce(prod.produit_sk, md5('-1' || '-' || '-1')) as produit_sk,
        s.loaded_at
    from {{ ref('stg_stockhistory') }} s
    left join {{ ref('dim_pharmacie') }} ph
        on s.PHA_ID = ph.PHA_ID
    left join {{ ref('dim_produit') }} prod
        on s.PHA_ID = prod.PHA_ID
        and s.PRD_ID = prod.PRD_ID
    {% if is_incremental() %}
    where s.loaded_at >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
    -- Déduplication : garder la dernière version par clé unique
    qualify row_number() over (
        partition by coalesce(ph.pharmacie_sk, md5('-1')), 
                     coalesce(prod.produit_sk, md5('-1' || '-' || '-1')), 
                     s.STH_DATE::date
        order by s.loaded_at desc
    ) = 1
)

select
    pharmacie_sk,
    produit_sk,
    date_stock,
    STH_STOCK                                               as quantite_stock,
    STH_STOCKDELTA                                          as delta_stock,
    STH_PRIXTARIF                                           as prix_tarif,
    STH_PRIXPUBLIC                                          as prix_public,
    STH_PAMP                                                as prix_achat_moyen_pondere,
    STH_PANET                                               as prix_achat_net,
    STH_STOCK * coalesce(STH_PANET, 0)                      as valeur_stock_pa,
    STH_STOCK * coalesce(STH_PRIXPUBLIC, 0)                 as valeur_stock_pv,
    STH_STOCK * (coalesce(STH_PRIXPUBLIC, 0) - coalesce(STH_PANET, 0))
                                                            as marge_latente,
    loaded_at
from stock_enriched
