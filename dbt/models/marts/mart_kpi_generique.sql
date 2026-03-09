{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'mois', 'FOU_ID', 'is_generique', 'univers'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'generique', 'laboratoire']
    )
}}

-- KPI Génériques et Parts de Marché Laboratoires avec Marge
with ventes_avec_prix as (
    select
        v.pharmacie_sk,
        v.produit_sk,
        v.date_vente,
        p.FOU_ID,
        f.FOU_NOM,
        p.is_generique,
        p.univers,
        v.ca_ht,
        v.ca_ttc,
        v.quantite_vendue,
        -- Prix d'achat pour calcul marge
        pr.prix_achat_net
    from {{ ref('fact_ventes') }} v
    inner join {{ ref('dim_produit') }} p
        on v.produit_sk = p.produit_sk
    left join {{ ref('dim_fournisseur') }} f
        on p.FOU_ID = f.FOU_ID
    left join {{ ref('fact_prix_journalier') }} pr
        on v.pharmacie_sk = pr.pharmacie_sk
        and v.produit_sk = pr.produit_sk
        and v.date_vente = pr.date_prix
    {% if is_incremental() %}
    where v.date_vente >= dateadd('month', -2, current_date())
    {% endif %}
),

ventes_generiques as (
    select
        pharmacie_sk,
        FOU_ID,
        FOU_NOM,
        is_generique,
        univers,
        date_trunc('month', date_vente)                     as mois,
        sum(ca_ht)                                          as ca_ht,
        sum(ca_ttc)                                         as ca_ttc,
        sum(quantite_vendue)                                as quantite_vendue,
        count(distinct produit_sk)                          as nb_produits,
        -- Calcul marge brute
        sum(ca_ht - (quantite_vendue * coalesce(prix_achat_net, 0)))  as marge_brute,
        sum(quantite_vendue * coalesce(prix_achat_net, 0))            as cout_achat_total
    from ventes_avec_prix
    group by
        pharmacie_sk,
        FOU_ID,
        FOU_NOM,
        is_generique,
        univers,
        date_trunc('month', date_vente)
),

-- Totaux par pharmacie/mois pour calcul PDM
totaux_pharmacie as (
    select
        pharmacie_sk,
        mois,
        sum(ca_ht)                                          as ca_ht_total,
        sum(ca_ttc)                                         as ca_ttc_total,
        sum(marge_brute)                                    as marge_brute_total
    from ventes_generiques
    group by pharmacie_sk, mois
),

-- Totaux génériques par pharmacie/mois
totaux_generiques as (
    select
        pharmacie_sk,
        mois,
        sum(ca_ht)                                          as ca_ht_generique,
        sum(ca_ttc)                                         as ca_ttc_generique,
        sum(marge_brute)                                    as marge_brute_generique
    from ventes_generiques
    where is_generique = true
    group by pharmacie_sk, mois
),

-- A-1 pour évolution
ventes_a1 as (
    select
        pharmacie_sk,
        FOU_ID,
        is_generique,
        univers,
        dateadd('year', 1, mois)                            as mois_cible,
        ca_ht                                               as ca_ht_a1,
        ca_ttc                                              as ca_ttc_a1,
        marge_brute                                         as marge_brute_a1
    from ventes_generiques
)

select
    vg.pharmacie_sk,
    vg.mois,
    vg.FOU_ID,
    vg.FOU_NOM,
    vg.is_generique,
    vg.univers,

    -- Volumes
    vg.ca_ht,
    vg.ca_ttc,
    vg.quantite_vendue,
    vg.nb_produits,

    -- Marge brute et taux de marge
    vg.marge_brute,
    vg.cout_achat_total,
    case
        when vg.ca_ht > 0
        then vg.marge_brute / vg.ca_ht
        else null
    end                                                     as taux_marge,

    -- Part de marché du labo dans la pharmacie
    case
        when tp.ca_ht_total > 0
        then vg.ca_ht / tp.ca_ht_total
        else null
    end                                                     as pdm_labo,

    -- CA total pharmacie (contexte)
    tp.ca_ht_total,

    -- Marge totale pharmacie
    tp.marge_brute_total,

    -- CA et marge générique total pharmacie
    tg.ca_ht_generique,
    tg.marge_brute_generique,

    -- Taux de générique dans la pharmacie
    case
        when tp.ca_ht_total > 0
        then tg.ca_ht_generique / tp.ca_ht_total
        else null
    end                                                     as taux_generique_pharmacie,

    -- Evolution vs A-1
    va1.ca_ht_a1,
    va1.marge_brute_a1,
    case
        when va1.ca_ht_a1 > 0
        then (vg.ca_ht - va1.ca_ht_a1) / va1.ca_ht_a1
        else null
    end                                                     as evolution_ca_vs_a1,
    case
        when va1.marge_brute_a1 > 0
        then (vg.marge_brute - va1.marge_brute_a1) / va1.marge_brute_a1
        else null
    end                                                     as evolution_marge_vs_a1

from ventes_generiques vg
left join totaux_pharmacie tp
    on vg.pharmacie_sk = tp.pharmacie_sk
    and vg.mois = tp.mois
left join totaux_generiques tg
    on vg.pharmacie_sk = tg.pharmacie_sk
    and vg.mois = tg.mois
left join ventes_a1 va1
    on vg.pharmacie_sk = va1.pharmacie_sk
    and vg.FOU_ID = va1.FOU_ID
    and vg.is_generique = va1.is_generique
    and vg.univers = va1.univers
    and vg.mois = va1.mois_cible
