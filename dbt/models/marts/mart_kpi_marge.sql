{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'produit_sk', 'date_jour'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'marge']
    )
}}

with ventes as (
    select
        pharmacie_sk,
        produit_sk,
        date_vente,
        sum(quantite_vendue)                                  as quantite_vendue,
        sum(ca_ht)                                            as ca_ht,
        sum(ca_ttc)                                           as ca_ttc
    from {{ ref('fact_ventes') }}
    group by pharmacie_sk, produit_sk, date_vente
),

prix as (
    select
        pharmacie_sk,
        produit_sk,
        date_prix,
        prix_tarif,
        prix_public,
        prix_achat_moyen_pondere,
        prix_achat_net
    from {{ ref('fact_prix_journalier') }}
    {% if is_incremental() %}
    where date_prix >= dateadd('month', -2, current_date())
    {% endif %}
)

select
    v.pharmacie_sk,
    v.produit_sk,
    v.date_vente                                          as date_jour,
    v.quantite_vendue,
    v.ca_ht,
    v.ca_ttc,
    p.prix_achat_net,
    p.prix_achat_moyen_pondere,
    p.prix_public,
    v.quantite_vendue * p.prix_achat_net                  as cout_achat_net,
    v.ca_ht - (v.quantite_vendue * p.prix_achat_net)      as marge_brute,
    case
        when v.ca_ht != 0
        then (v.ca_ht - (v.quantite_vendue * p.prix_achat_net)) / v.ca_ht
        else null
    end                                                    as taux_marge
from ventes v
inner join prix p
    on v.pharmacie_sk = p.pharmacie_sk
    and v.produit_sk = p.produit_sk
    and v.date_vente = p.date_prix
