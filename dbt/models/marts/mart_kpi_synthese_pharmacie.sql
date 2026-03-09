{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'synthese', 'dashboard']
    )
}}

-- Synthese KPIs par pharmacie/mois - PRET POUR DASHBOARD
-- Toutes les metriques principales agregees, aucun calcul supplementaire requis

with ca_evolution as (
    select
        pharmacie_sk,
        mois,
        sum(ca_ht)                                          as ca_ht,
        sum(ca_ttc)                                         as ca_ttc,
        sum(ca_ht_a1)                                       as ca_ht_a1,
        max(ca_ht_ytd)                                      as ca_ht_ytd,
        max(ca_ht_ytd_a1)                                   as ca_ht_ytd_a1,
        max(ca_ht_12dm)                                     as ca_ht_12dm,
        max(ca_ht_12dm_a1)                                  as ca_ht_12dm_a1
    from {{ ref('mart_kpi_ca_evolution') }}
    group by pharmacie_sk, mois
),

stock_valorisation as (
    select
        pharmacie_sk,
        mois,
        sum(valeur_stock_pa_fin_mois)                       as valeur_stock_pa,
        sum(valeur_stock_pv_fin_mois)                       as valeur_stock_pv,
        sum(stock_fin_mois)                                 as stock_total_unites,
        avg(couverture_stock_jours)                         as couverture_stock_jours_moy,
        count(case when stock_dormant then 1 end)           as nb_produits_dormants,
        count(*)                                            as nb_produits_en_stock
    from {{ ref('mart_kpi_stock_valorisation') }}
    group by pharmacie_sk, mois
),

generique_summary as (
    select
        pharmacie_sk,
        mois,
        -- Totaux tous produits
        sum(ca_ht)                                          as ca_ht_total,
        sum(marge_brute)                                    as marge_brute_total,
        -- Totaux generiques uniquement
        sum(case when is_generique then ca_ht else 0 end)   as ca_ht_generique,
        sum(case when is_generique then marge_brute else 0 end) as marge_brute_generique,
        -- Comptages
        count(distinct case when is_generique then FOU_ID end) as nb_labos_generiques,
        sum(case when is_generique then nb_produits else 0 end) as nb_produits_generiques
    from {{ ref('mart_kpi_generique') }}
    group by pharmacie_sk, mois
),

dormants as (
    select
        pharmacie_sk,
        count(case when is_dormant_6m then 1 end)           as nb_dormants_6m,
        count(case when is_dormant_12m then 1 end)          as nb_dormants_12m,
        count(*)                                            as nb_produits_total,
        sum(valeur_stock_pa)                                as valeur_stock_dormant
    from {{ ref('mart_kpi_dormant') }}
    group by pharmacie_sk
)

select
    ca.pharmacie_sk,
    ca.mois,

    -- ============ CA & EVOLUTION ============
    ca.ca_ht,
    ca.ca_ttc,
    ca.ca_ht_a1,
    case
        when ca.ca_ht_a1 > 0
        then (ca.ca_ht - ca.ca_ht_a1) / ca.ca_ht_a1
        else null
    end                                                     as evolution_ca_vs_a1,

    ca.ca_ht_ytd,
    ca.ca_ht_ytd_a1,
    case
        when ca.ca_ht_ytd_a1 > 0
        then (ca.ca_ht_ytd - ca.ca_ht_ytd_a1) / ca.ca_ht_ytd_a1
        else null
    end                                                     as evolution_ytd_vs_a1,

    ca.ca_ht_12dm,
    ca.ca_ht_12dm_a1,
    case
        when ca.ca_ht_12dm_a1 > 0
        then (ca.ca_ht_12dm - ca.ca_ht_12dm_a1) / ca.ca_ht_12dm_a1
        else null
    end                                                     as evolution_12dm_vs_a1,

    -- ============ MARGE GLOBALE ============
    g.marge_brute_total                                     as marge_brute,
    case
        when g.ca_ht_total > 0
        then g.marge_brute_total / g.ca_ht_total
        else null
    end                                                     as taux_marge,

    -- ============ STOCK ============
    s.valeur_stock_pa,
    s.valeur_stock_pv,
    s.stock_total_unites,
    s.couverture_stock_jours_moy,
    s.nb_produits_en_stock,
    s.nb_produits_dormants,

    -- KPI: Ratio Valeur Stock / CA Annuel (%)
    case
        when ca.ca_ht_ytd > 0
        then (s.valeur_stock_pa / ca.ca_ht_ytd) * 100
        else null
    end                                                     as ratio_stock_ca_annuel_pct,

    -- ============ GENERIQUE ============
    g.ca_ht_generique,
    g.marge_brute_generique,
    case
        when g.ca_ht_total > 0
        then g.ca_ht_generique / g.ca_ht_total
        else null
    end                                                     as taux_generique,
    case
        when g.ca_ht_generique > 0
        then g.marge_brute_generique / g.ca_ht_generique
        else null
    end                                                     as taux_marge_generique,
    g.nb_labos_generiques,
    g.nb_produits_generiques,

    -- ============ DORMANTS ============
    d.nb_dormants_6m,
    d.nb_dormants_12m,
    case
        when d.nb_produits_total > 0
        then d.nb_dormants_6m::float / d.nb_produits_total
        else null
    end                                                     as pct_dormants_6m,
    case
        when d.nb_produits_total > 0
        then d.nb_dormants_12m::float / d.nb_produits_total
        else null
    end                                                     as pct_dormants_12m,
    d.valeur_stock_dormant

from ca_evolution ca
left join stock_valorisation s
    on ca.pharmacie_sk = s.pharmacie_sk
    and ca.mois = s.mois
left join generique_summary g
    on ca.pharmacie_sk = g.pharmacie_sk
    and ca.mois = g.mois
left join dormants d
    on ca.pharmacie_sk = d.pharmacie_sk
