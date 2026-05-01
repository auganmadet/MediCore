{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'marge', 'agrege']
    )
}}

-- Marge agrégée par produit (toutes dates confondues)
-- Utilisé par : D4 "Top 20 produits par marge"

with marge as (
    select
        m.pharmacie_sk,
        m.produit_sk,
        p.PRD_NOM,
        p.univers,
        sum(m.marge_brute)                                  as marge_brute,
        sum(m.ca_ht)                                        as ca_ht,
        sum(m.quantite_vendue)                              as quantite_vendue,
        case
            when sum(m.ca_ht) > 0
            then sum(m.marge_brute) / sum(m.ca_ht)
            else null
        end                                                 as taux_marge
    from {{ ref('mart_kpi_marge') }} m
    inner join {{ ref('dim_produit') }} p
        on m.produit_sk = p.produit_sk
    group by m.pharmacie_sk, m.produit_sk, p.PRD_NOM, p.univers
)

select * from marge
