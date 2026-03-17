{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'produit_sk'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'ventes', 'agrege']
    )
}}

-- Ventes agrégées par produit avec nom
-- Utilisé par : D15 "Top produits vendus"

select
    v.pharmacie_sk,
    v.produit_sk,
    p.PRD_NOM,
    sum(v.quantite_vendue)                                  as quantite_vendue,
    sum(v.ca_ht)                                            as ca_ht,
    sum(v.ca_ttc)                                           as ca_ttc,
    sum(v.nb_lignes)                                        as nb_lignes
from {{ ref('fact_ventes') }} v
inner join {{ ref('dim_produit') }} p
    on v.produit_sk = p.produit_sk
{% if is_incremental() %}
where v.date_vente >= dateadd('month', -2, current_date())
{% endif %}
group by v.pharmacie_sk, v.produit_sk, p.PRD_NOM
