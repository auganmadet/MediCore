{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'stock_valorisation']
    )
}}

with stock_mensuel as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_stock)                     as mois,
        avg(quantite_stock)                                 as stock_moyen,
        avg(valeur_stock_pa)                                as valeur_stock_pa_moyenne,
        avg(valeur_stock_pv)                                as valeur_stock_pv_moyenne,
        avg(marge_latente)                                  as marge_latente_moyenne,
        max_by(quantite_stock, date_stock)                  as stock_fin_mois,
        max_by(valeur_stock_pa, date_stock)                 as valeur_stock_pa_fin_mois,
        max_by(valeur_stock_pv, date_stock)                 as valeur_stock_pv_fin_mois,
        max_by(prix_achat_net, date_stock)                  as prix_achat_net_fin,
        min_by(prix_achat_net, date_stock)                  as prix_achat_net_debut
    from {{ ref('fact_stock_valorisation') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_stock)
),

ventes_mensuelles as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_vente)                     as mois,
        sum(quantite_vendue)                                as quantite_vendue
    from {{ ref('fact_ventes') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_vente)
)

select
    s.pharmacie_sk,
    s.produit_sk,
    s.mois,

    -- Stock fin de mois
    s.stock_fin_mois,
    s.valeur_stock_pa_fin_mois,
    s.valeur_stock_pv_fin_mois,

    -- Moyennes mensuelles
    s.stock_moyen,
    s.valeur_stock_pa_moyenne,
    s.valeur_stock_pv_moyenne,
    s.marge_latente_moyenne,

    -- Couverture de stock en jours (stock fin mois / ventes moy jour)
    case
        when coalesce(v.quantite_vendue, 0) > 0
        then s.stock_fin_mois * 30.0 / v.quantite_vendue
        else null
    end                                                     as couverture_stock_jours,

    -- Variation prix d'achat dans le mois (detection inflation)
    case
        when s.prix_achat_net_debut > 0
        then (s.prix_achat_net_fin - s.prix_achat_net_debut) / s.prix_achat_net_debut
        else null
    end                                                     as variation_prix_achat,

    -- Stock dormant (stock > 0 mais aucune vente dans le mois)
    case
        when s.stock_moyen > 0 and coalesce(v.quantite_vendue, 0) = 0
        then true
        else false
    end                                                     as stock_dormant,

    -- Ventes pour contexte
    coalesce(v.quantite_vendue, 0)                          as quantite_vendue

from stock_mensuel s
left join ventes_mensuelles v
    on s.pharmacie_sk = v.pharmacie_sk
    and s.produit_sk = v.produit_sk
    and s.mois = v.mois
