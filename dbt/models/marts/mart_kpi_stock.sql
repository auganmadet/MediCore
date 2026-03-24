{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'produit_sk', 'mois'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'stock']
    )
}}

with stock_journalier as (
    select
        pharmacie_sk,
        produit_sk,
        date_mouvement,
        stock_apres,
        date_trunc('month', date_mouvement) as mois
    from {{ ref('fact_stock_mouvement') }}
    {% if is_incremental() %}
    where date_mouvement >= dateadd('month', -2, current_date())
    {% endif %}
),

stock_mensuel as (
    select
        pharmacie_sk,
        produit_sk,
        mois,
        avg(stock_apres)                                    as stock_moyen,
        min(stock_apres)                                    as stock_min,
        max(stock_apres)                                    as stock_max,
        count(case when stock_apres = 0 then 1 end)         as nb_jours_rupture,
        count(*)                                             as nb_jours_mouvement
    from stock_journalier
    group by pharmacie_sk, produit_sk, mois
),

ventes_mensuelles as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_vente) as mois,
        sum(quantite_vendue)            as quantite_vendue
    from {{ ref('fact_ventes') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_vente)
)

select
    s.pharmacie_sk,
    s.produit_sk,
    s.mois,
    s.stock_moyen,
    s.stock_min,
    s.stock_max,
    s.nb_jours_rupture,
    s.nb_jours_mouvement,
    coalesce(v.quantite_vendue, 0)                          as quantite_vendue,
    case
        when s.stock_moyen > 0
        then coalesce(v.quantite_vendue, 0) / s.stock_moyen
        else null
    end                                                      as rotation_stock,
    case
        when s.nb_jours_mouvement > 0
        then s.nb_jours_rupture::float / s.nb_jours_mouvement
        else null
    end                                                      as taux_rupture_stock
from stock_mensuel s
left join ventes_mensuelles v
    on s.pharmacie_sk = v.pharmacie_sk
    and s.produit_sk = v.produit_sk
    and s.mois = v.mois