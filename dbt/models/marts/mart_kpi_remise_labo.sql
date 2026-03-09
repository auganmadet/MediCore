{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'fournisseur_sk', 'mois'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'remise', 'laboratoire']
    )
}}

-- KPI Remise pondérée par laboratoire/fournisseur
with commandes_avec_remise as (
    select
        c.pharmacie_sk,
        c.fournisseur_sk,
        f.FOU_ID,
        f.FOU_NOM,
        date_trunc('month', c.date_commande)                as mois,
        c.quantite_commandee,
        c.montant_pahtnet,
        c.remise_moyenne
    from {{ ref('fact_commandes') }} c
    left join {{ ref('dim_fournisseur') }} f
        on c.fournisseur_sk = f.fournisseur_sk
    where c.remise_moyenne is not null
    {% if is_incremental() %}
      and c.date_commande >= dateadd('month', -2, current_date())
    {% endif %}
),

-- Agrégation mensuelle par labo avec remise pondérée
remise_mensuelle as (
    select
        pharmacie_sk,
        fournisseur_sk,
        FOU_ID,
        FOU_NOM,
        mois,
        sum(quantite_commandee)                             as quantite_totale,
        sum(montant_pahtnet)                                as montant_total,
        count(*)                                            as nb_commandes,
        -- Remise pondérée par quantité
        sum(remise_moyenne * quantite_commandee) 
            / nullif(sum(quantite_commandee), 0)            as remise_ponderee_qte,
        -- Remise pondérée par montant
        sum(remise_moyenne * montant_pahtnet) 
            / nullif(sum(montant_pahtnet), 0)               as remise_ponderee_montant,
        -- Remise moyenne simple
        avg(remise_moyenne)                                 as remise_moyenne
    from commandes_avec_remise
    group by pharmacie_sk, fournisseur_sk, FOU_ID, FOU_NOM, mois
),

-- Totaux par pharmacie pour contexte
totaux_pharmacie as (
    select
        pharmacie_sk,
        mois,
        sum(montant_total)                                  as montant_total_pharmacie,
        sum(quantite_totale)                                as quantite_totale_pharmacie
    from remise_mensuelle
    group by pharmacie_sk, mois
),

-- A-1 pour évolution
remise_a1 as (
    select
        pharmacie_sk,
        fournisseur_sk,
        dateadd('year', 1, mois)                            as mois_cible,
        remise_ponderee_qte                                 as remise_ponderee_a1,
        montant_total                                       as montant_total_a1
    from remise_mensuelle
)

select
    rm.pharmacie_sk,
    rm.fournisseur_sk,
    rm.FOU_ID,
    rm.FOU_NOM,
    rm.mois,

    -- Volumes
    rm.quantite_totale,
    rm.montant_total,
    rm.nb_commandes,

    -- Remises
    rm.remise_moyenne,
    rm.remise_ponderee_qte,
    rm.remise_ponderee_montant,

    -- Part du labo dans les achats
    case
        when tp.montant_total_pharmacie > 0
        then rm.montant_total / tp.montant_total_pharmacie
        else null
    end                                                     as pdm_achats_labo,

    -- Contexte pharmacie
    tp.montant_total_pharmacie,
    tp.quantite_totale_pharmacie,

    -- Evolution vs A-1
    ra1.remise_ponderee_a1,
    case
        when ra1.remise_ponderee_a1 > 0
        then (rm.remise_ponderee_qte - ra1.remise_ponderee_a1) / ra1.remise_ponderee_a1
        else null
    end                                                     as evolution_remise_vs_a1,
    ra1.montant_total_a1,
    case
        when ra1.montant_total_a1 > 0
        then (rm.montant_total - ra1.montant_total_a1) / ra1.montant_total_a1
        else null
    end                                                     as evolution_montant_vs_a1

from remise_mensuelle rm
left join totaux_pharmacie tp
    on rm.pharmacie_sk = tp.pharmacie_sk
    and rm.mois = tp.mois
left join remise_a1 ra1
    on rm.pharmacie_sk = ra1.pharmacie_sk
    and rm.fournisseur_sk = ra1.fournisseur_sk
    and rm.mois = ra1.mois_cible
