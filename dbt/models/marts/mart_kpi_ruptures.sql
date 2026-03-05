{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'ruptures']
    )
}}

with ruptures_mensuelles as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_rupture)   as mois,
        sum(nb_lignes_manquantes)           as nb_lignes_manquantes,
        sum(nb_boites_manquantes)           as nb_boites_manquantes,
        sum(nb_clients_impactes)            as nb_clients_impactes,
        sum(nb_factures_impactees)          as nb_factures_impactees,
        count(distinct date_rupture)        as nb_jours_rupture
    from {{ ref('fact_ruptures') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_rupture)
),

ventes_mensuelles as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_vente)     as mois,
        sum(quantite_vendue)                as quantite_vendue,
        sum(ca_ht)                          as ca_ht,
        sum(nb_lignes)                      as nb_lignes_vendues
    from {{ ref('fact_ventes') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_vente)
),

prix_moyen_mensuel as (
    select
        pharmacie_sk,
        produit_sk,
        date_trunc('month', date_prix)      as mois,
        avg(prix_achat_net)                 as prix_achat_net_moyen,
        avg(prix_public)                    as prix_public_moyen
    from {{ ref('fact_prix_journalier') }}
    group by pharmacie_sk, produit_sk, date_trunc('month', date_prix)
)

select
    r.pharmacie_sk,
    r.produit_sk,
    r.mois,

    -- Volumes de rupture (demande non servie)
    r.nb_lignes_manquantes,
    r.nb_boites_manquantes,
    r.nb_clients_impactes,
    r.nb_factures_impactees,
    r.nb_jours_rupture,

    -- Volumes de vente (contexte)
    coalesce(v.quantite_vendue, 0)          as quantite_vendue,
    coalesce(v.nb_lignes_vendues, 0)        as nb_lignes_vendues,
    coalesce(v.ca_ht, 0)                   as ca_ht,

    -- Taux de rupture demande (lignes non satisfaites / total lignes)
    case
        when coalesce(v.nb_lignes_vendues, 0) + r.nb_lignes_manquantes > 0
        then r.nb_lignes_manquantes::float
             / (coalesce(v.nb_lignes_vendues, 0) + r.nb_lignes_manquantes)
        else null
    end                                     as taux_rupture_demande,

    -- Estimation CA perdu (boites manquantes * prix public moyen)
    case
        when p.prix_public_moyen is not null
        then r.nb_boites_manquantes * p.prix_public_moyen
        else null
    end                                     as ca_estime_perdu,

    -- Estimation marge perdue (boites manquantes * (prix public - prix achat))
    case
        when p.prix_public_moyen is not null and p.prix_achat_net_moyen is not null
        then r.nb_boites_manquantes * (p.prix_public_moyen - p.prix_achat_net_moyen)
        else null
    end                                     as marge_estimee_perdue

from ruptures_mensuelles r
left join ventes_mensuelles v
    on r.pharmacie_sk = v.pharmacie_sk
    and r.produit_sk = v.produit_sk
    and r.mois = v.mois
left join prix_moyen_mensuel p
    on r.pharmacie_sk = p.pharmacie_sk
    and r.produit_sk = p.produit_sk
    and r.mois = p.mois
