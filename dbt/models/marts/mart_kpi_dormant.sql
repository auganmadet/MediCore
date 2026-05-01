{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'dormant', 'stock'],
        cluster_by=['statut_dormant', 'PHA_ID']
    )
}}

-- KPI Produits dormants : sans vente depuis 6 ou 12 mois
with produits_avec_stock as (
    select
        p.produit_sk,
        p.PHA_ID,
        p.PRD_ID,
        p.PRD_NOM,
        p.FOU_ID,
        p.univers,
        p.is_generique,
        p.PRD_STOCK,
        p.derniere_vente,
        f.FOU_NOM
    from {{ ref('dim_produit') }} p
    left join {{ ref('dim_fournisseur') }} f
        on p.FOU_ID = f.FOU_ID
    where p.PRD_ID != -1
      and p.PRD_STOCK > 0
),

-- Dernière vente effective par produit (via fact_ventes)
derniere_vente_reelle as (
    select
        produit_sk,
        max(date_vente)                                 as derniere_vente_fact
    from {{ ref('fact_ventes') }}
    group by produit_sk
),

-- Valorisation stock actuelle
stock_actuel as (
    select
        produit_sk,
        pharmacie_sk,
        max_by(valeur_stock_pa, date_stock)             as valeur_stock_pa,
        max_by(valeur_stock_pv, date_stock)             as valeur_stock_pv,
        max_by(quantite_stock, date_stock)              as quantite_stock,
        max(date_stock)                                 as date_stock
    from {{ ref('fact_stock_valorisation') }}
    group by produit_sk, pharmacie_sk
)

select
    ps.produit_sk,
    ph.pharmacie_sk,
    ps.PHA_ID,
    ps.PRD_ID,
    ps.PRD_NOM,
    ps.FOU_ID,
    ps.FOU_NOM,
    ps.univers,
    ps.is_generique,

    -- Stock actuel
    coalesce(sa.quantite_stock, ps.PRD_STOCK)           as quantite_stock,
    sa.valeur_stock_pa,
    sa.valeur_stock_pv,

    -- Dates de dernière vente
    ps.derniere_vente                                   as derniere_vente_produit,
    dv.derniere_vente_fact                              as derniere_vente_effective,
    coalesce(dv.derniere_vente_fact, ps.derniere_vente) as derniere_vente,

    -- Calcul des jours sans vente
    datediff('day',
        coalesce(dv.derniere_vente_fact, ps.derniere_vente),
        current_date()
    )                                                   as jours_sans_vente,

    -- Classification dormant
    case
        when coalesce(dv.derniere_vente_fact, ps.derniere_vente) is null
            then 'JAMAIS_VENDU'
        when datediff('day', coalesce(dv.derniere_vente_fact, ps.derniere_vente), current_date()) >= 365
            then 'DORMANT_12M'
        when datediff('day', coalesce(dv.derniere_vente_fact, ps.derniere_vente), current_date()) >= 180
            then 'DORMANT_6M'
        when datediff('day', coalesce(dv.derniere_vente_fact, ps.derniere_vente), current_date()) >= 90
            then 'DORMANT_3M'
        else 'ACTIF'
    end                                                 as statut_dormant,

    -- Flags binaires pour filtrage
    case
        when coalesce(dv.derniere_vente_fact, ps.derniere_vente) is null
            or datediff('day', coalesce(dv.derniere_vente_fact, ps.derniere_vente), current_date()) >= 180
        then true else false
    end                                                 as is_dormant_6m,

    case
        when coalesce(dv.derniere_vente_fact, ps.derniere_vente) is null
            or datediff('day', coalesce(dv.derniere_vente_fact, ps.derniere_vente), current_date()) >= 365
        then true else false
    end                                                 as is_dormant_12m,

    -- Marge latente bloquée (capital immobilisé)
    coalesce(sa.valeur_stock_pv, 0) - coalesce(sa.valeur_stock_pa, 0)
                                                        as marge_latente_bloquee

from produits_avec_stock ps
inner join {{ ref('dim_pharmacie') }} ph
    on ps.PHA_ID = ph.PHA_ID
left join derniere_vente_reelle dv
    on ps.produit_sk = dv.produit_sk
left join stock_actuel sa
    on ps.produit_sk = sa.produit_sk
    and ph.pharmacie_sk = sa.pharmacie_sk
