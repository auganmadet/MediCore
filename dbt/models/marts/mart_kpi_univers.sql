{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'mois', 'univers'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'univers', 'dashboard']
    )
}}

-- KPI par Univers (RX, OTC, PARA, HORS_REMB) - pret pour dashboard
-- Agregation par pharmacie/mois/univers avec marge et parts de marche

with ventes_univers as (
    select
        pharmacie_sk,
        mois,
        univers,
        sum(ca_ht)                                          as ca_ht,
        sum(ca_ttc)                                         as ca_ttc,
        sum(quantite_vendue)                                as quantite_vendue,
        sum(marge_brute)                                    as marge_brute,
        sum(cout_achat_total)                               as cout_achat_total,
        count(distinct FOU_ID)                              as nb_laboratoires,
        sum(nb_produits)                                    as nb_produits
    from {{ ref('mart_kpi_generique') }}
    {% if is_incremental() %}
    where mois >= dateadd('month', -2, current_date())
    {% endif %}
    group by pharmacie_sk, mois, univers
),

-- Totaux par pharmacie pour calcul des parts
totaux_pharmacie as (
    select
        pharmacie_sk,
        mois,
        sum(ca_ht)                                          as ca_ht_total,
        sum(ca_ttc)                                         as ca_ttc_total,
        sum(marge_brute)                                    as marge_brute_total
    from ventes_univers
    group by pharmacie_sk, mois
),

-- A-1 pour evolution
univers_a1 as (
    select
        pharmacie_sk,
        univers,
        dateadd('year', 1, mois)                            as mois_cible,
        ca_ht                                               as ca_ht_a1,
        marge_brute                                         as marge_brute_a1
    from ventes_univers
)

select
    u.pharmacie_sk,
    u.mois,
    u.univers,

    -- Volumes
    u.ca_ht,
    u.ca_ttc,
    u.quantite_vendue,
    u.nb_laboratoires,
    u.nb_produits,

    -- Marge
    u.marge_brute,
    case
        when u.ca_ht > 0
        then u.marge_brute / u.ca_ht
        else null
    end                                                     as taux_marge,

    -- Part de l'univers dans le CA pharmacie
    case
        when t.ca_ht_total > 0
        then u.ca_ht / t.ca_ht_total
        else null
    end                                                     as pct_ca_univers,

    -- Part de l'univers dans la marge pharmacie
    case
        when t.marge_brute_total > 0
        then u.marge_brute / t.marge_brute_total
        else null
    end                                                     as pct_marge_univers,

    -- Contexte pharmacie
    t.ca_ht_total,
    t.marge_brute_total,

    -- Evolution vs A-1
    ua1.ca_ht_a1,
    case
        when ua1.ca_ht_a1 > 0
        then (u.ca_ht - ua1.ca_ht_a1) / ua1.ca_ht_a1
        else null
    end                                                     as evolution_ca_vs_a1,

    ua1.marge_brute_a1,
    case
        when ua1.marge_brute_a1 > 0
        then (u.marge_brute - ua1.marge_brute_a1) / ua1.marge_brute_a1
        else null
    end                                                     as evolution_marge_vs_a1

from ventes_univers u
left join totaux_pharmacie t
    on u.pharmacie_sk = t.pharmacie_sk
    and u.mois = t.mois
left join univers_a1 ua1
    on u.pharmacie_sk = ua1.pharmacie_sk
    and u.univers = ua1.univers
    and u.mois = ua1.mois_cible
