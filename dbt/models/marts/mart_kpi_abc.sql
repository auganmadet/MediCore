{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'abc']
    )
}}

with ventes_mensuelles as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_vente)                     as mois,
        sum(ca_ht)                                          as ca_ht,
        sum(quantite_vendue)                                as quantite_vendue,
        sum(nb_lignes)                                      as nb_lignes
    from {{ ref('fact_ventes') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_vente)
),

ca_total_pharmacie as (
    select
        pharmacie_sk,
        mois,
        sum(ca_ht)                                          as ca_total,
        count(distinct produit_sk)                          as nb_produits_total
    from ventes_mensuelles
    group by pharmacie_sk, mois
),

ranked as (
    select
        v.pharmacie_sk,
        v.produit_sk,
        v.mois,
        v.ca_ht,
        v.quantite_vendue,
        v.nb_lignes,
        t.ca_total,
        t.nb_produits_total,
        v.ca_ht / nullif(t.ca_total, 0)                    as pct_ca,
        row_number() over (
            partition by v.pharmacie_sk, v.mois
            order by v.ca_ht desc
        )                                                   as rang,
        sum(v.ca_ht) over (
            partition by v.pharmacie_sk, v.mois
            order by v.ca_ht desc
            rows unbounded preceding
        )                                                   as ca_cumule
    from ventes_mensuelles v
    inner join ca_total_pharmacie t
        on v.pharmacie_sk = t.pharmacie_sk
        and v.mois = t.mois
)

select
    pharmacie_sk,
    produit_sk,
    mois,
    rang,
    ca_ht,
    quantite_vendue,
    nb_lignes,
    ca_total,
    nb_produits_total,
    pct_ca,
    ca_cumule / nullif(ca_total, 0)                         as pct_ca_cumule,
    case
        when ca_cumule / nullif(ca_total, 0) <= 0.80 then 'A'
        when ca_cumule / nullif(ca_total, 0) <= 0.95 then 'B'
        else 'C'
    end                                                     as classe_abc
from ranked
