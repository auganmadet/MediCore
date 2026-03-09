{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'ca', 'evolution']
    )
}}

-- KPI Evolution CA : année en cours vs A-1, 12 derniers mois glissants
with ventes_mensuelles as (
    select
        v.pharmacie_sk,
        date_trunc('month', v.date_vente)               as mois,
        date_trunc('year', v.date_vente)                as annee,
        sum(v.ca_ht)                                    as ca_ht,
        sum(v.ca_ttc)                                   as ca_ttc,
        sum(v.quantite_vendue)                          as quantite_vendue,
        count(distinct v.date_vente)                    as nb_jours_vente
    from {{ ref('fact_ventes') }} v
    group by v.pharmacie_sk, date_trunc('month', v.date_vente), date_trunc('year', v.date_vente)
),

-- CA par mois avec mois équivalent A-1
ca_avec_a1 as (
    select
        vm.pharmacie_sk,
        vm.mois,
        vm.annee,
        vm.ca_ht,
        vm.ca_ttc,
        vm.quantite_vendue,
        vm.nb_jours_vente,
        -- Mois équivalent année précédente
        vm_a1.ca_ht                                     as ca_ht_a1,
        vm_a1.ca_ttc                                    as ca_ttc_a1,
        vm_a1.quantite_vendue                           as quantite_vendue_a1
    from ventes_mensuelles vm
    left join ventes_mensuelles vm_a1
        on vm.pharmacie_sk = vm_a1.pharmacie_sk
        and vm.mois = dateadd('year', 1, vm_a1.mois)
),

-- CA cumulé année en cours
ca_ytd as (
    select
        pharmacie_sk,
        annee,
        sum(ca_ht)                                      as ca_ht_ytd,
        sum(ca_ttc)                                     as ca_ttc_ytd,
        sum(quantite_vendue)                            as quantite_ytd,
        sum(ca_ht_a1)                                   as ca_ht_ytd_a1,
        sum(ca_ttc_a1)                                  as ca_ttc_ytd_a1
    from ca_avec_a1
    group by pharmacie_sk, annee
),

-- CA 12 derniers mois glissants (rolling 12 months)
ca_12dm as (
    select
        vm.pharmacie_sk,
        vm.mois,
        sum(vm2.ca_ht)                                  as ca_ht_12dm,
        sum(vm2.ca_ttc)                                 as ca_ttc_12dm,
        sum(vm2.quantite_vendue)                        as quantite_12dm
    from ventes_mensuelles vm
    inner join ventes_mensuelles vm2
        on vm.pharmacie_sk = vm2.pharmacie_sk
        and vm2.mois > dateadd('month', -12, vm.mois)
        and vm2.mois <= vm.mois
    group by vm.pharmacie_sk, vm.mois
),

-- CA 12DM période équivalente A-1
ca_12dm_a1 as (
    select
        c1.pharmacie_sk,
        c1.mois,
        c2.ca_ht_12dm                                   as ca_ht_12dm_a1,
        c2.ca_ttc_12dm                                  as ca_ttc_12dm_a1
    from ca_12dm c1
    left join ca_12dm c2
        on c1.pharmacie_sk = c2.pharmacie_sk
        and c1.mois = dateadd('year', 1, c2.mois)
)

select
    ca.pharmacie_sk,
    ca.mois,
    ca.annee,

    -- CA mensuel
    ca.ca_ht,
    ca.ca_ttc,
    ca.quantite_vendue,
    ca.nb_jours_vente,

    -- Comparaison A-1 mensuelle
    ca.ca_ht_a1,
    ca.ca_ttc_a1,
    case
        when ca.ca_ht_a1 > 0
        then (ca.ca_ht - ca.ca_ht_a1) / ca.ca_ht_a1
        else null
    end                                                 as evolution_ca_ht_vs_a1,

    -- YTD (Year-To-Date)
    ytd.ca_ht_ytd,
    ytd.ca_ttc_ytd,
    ytd.ca_ht_ytd_a1,
    case
        when ytd.ca_ht_ytd_a1 > 0
        then (ytd.ca_ht_ytd - ytd.ca_ht_ytd_a1) / ytd.ca_ht_ytd_a1
        else null
    end                                                 as evolution_ytd_vs_a1,

    -- 12 Derniers Mois (12DM / Rolling 12 months)
    dm.ca_ht_12dm,
    dm.ca_ttc_12dm,
    dm_a1.ca_ht_12dm_a1,
    case
        when dm_a1.ca_ht_12dm_a1 > 0
        then (dm.ca_ht_12dm - dm_a1.ca_ht_12dm_a1) / dm_a1.ca_ht_12dm_a1
        else null
    end                                                 as evolution_12dm_vs_a1

from ca_avec_a1 ca
left join ca_ytd ytd
    on ca.pharmacie_sk = ytd.pharmacie_sk
    and ca.annee = ytd.annee
left join ca_12dm dm
    on ca.pharmacie_sk = dm.pharmacie_sk
    and ca.mois = dm.mois
left join ca_12dm_a1 dm_a1
    on ca.pharmacie_sk = dm_a1.pharmacie_sk
    and ca.mois = dm_a1.mois
