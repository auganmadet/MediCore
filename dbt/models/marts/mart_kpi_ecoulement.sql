{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'ecoulement']
    )
}}

with commandes_mensuelles as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_commande)  as mois,
        sum(quantite_commandee)             as quantite_commandee,
        sum(montant_pahtnet)                as montant_commande,
        count(distinct commande_id)         as nb_commandes
    from {{ ref('fact_commandes') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_commande)
),

ventes_mensuelles as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_vente) as mois,
        sum(quantite_vendue)            as quantite_vendue,
        sum(ca_ht)                      as ca_ht
    from {{ ref('fact_ventes') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_vente)
)

select
    coalesce(c.pharmacie_sk, v.pharmacie_sk) as pharmacie_sk,
    coalesce(c.produit_sk, v.produit_sk)     as produit_sk,
    coalesce(c.mois, v.mois)                 as mois,
    coalesce(c.quantite_commandee, 0)        as quantite_commandee,
    coalesce(c.montant_commande, 0)          as montant_commande,
    coalesce(c.nb_commandes, 0)              as nb_commandes,
    coalesce(v.quantite_vendue, 0)           as quantite_vendue,
    coalesce(v.ca_ht, 0)                     as ca_ht,
    case
        when coalesce(c.quantite_commandee, 0) > 0
        then coalesce(v.quantite_vendue, 0)::float / c.quantite_commandee
        else null
    end                                       as taux_ecoulement
from commandes_mensuelles c
full outer join ventes_mensuelles v
    on c.pharmacie_sk = v.pharmacie_sk
    and c.produit_sk = v.produit_sk
    and c.mois = v.mois
