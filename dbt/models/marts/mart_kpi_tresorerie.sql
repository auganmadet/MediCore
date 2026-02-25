{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'tresorerie']
    )
}}

with tresorerie_mensuelle as (
    select
        pharmacie_sk,
        date_trunc('month', date_jour)      as mois,
        sum(montant_especes)                as montant_especes,
        sum(montant_cheques)                as montant_cheques,
        sum(montant_cb)                     as montant_cb,
        sum(montant_mutuelle)               as montant_mutuelle,
        sum(montant_virement)               as montant_virement,
        sum(montant_centre)                 as montant_centre,
        sum(montant_subrogation)            as montant_subrogation,
        sum(ca_total_jour)                  as ca_total,
        sum(nb_De_Factures)                 as nb_factures,
        sum(nb_De_Subro)                    as nb_subrogations,
        sum(marge_remboursable)             as marge_remboursable,
        sum(marge_non_remboursable)         as marge_non_remboursable,
        sum(marge_totale)                   as marge_totale,
        sum(remises_totales)                as remises_totales,
        sum(tva_taux1)                      as tva_taux1,
        sum(tva_taux2)                      as tva_taux2,
        sum(tva_taux3)                      as tva_taux3,
        sum(tva_taux4)                      as tva_taux4,
        sum(tva_taux5)                      as tva_taux5,
        sum(ca_retrocessions)               as ca_retrocessions,
        sum(points_fidelite)                as points_fidelite,
        count(distinct date_jour)           as nb_jours_activite
    from {{ ref('fact_tresorerie') }}
    group by pharmacie_sk, date_trunc('month', date_jour)
)

select
    pharmacie_sk,
    mois,

    -- Volumes
    ca_total,
    nb_factures,
    nb_jours_activite,

    -- Panier moyen
    case
        when nb_factures > 0
        then ca_total / nb_factures
        else null
    end                                     as panier_moyen,

    -- Repartition modes de paiement (%)
    case when ca_total > 0
        then montant_especes / ca_total
        else null
    end                                     as pct_especes,
    case when ca_total > 0
        then montant_cheques / ca_total
        else null
    end                                     as pct_cheques,
    case when ca_total > 0
        then montant_cb / ca_total
        else null
    end                                     as pct_cb,
    case when ca_total > 0
        then (montant_mutuelle + montant_centre + montant_subrogation) / ca_total
        else null
    end                                     as pct_tiers_payant,
    case when ca_total > 0
        then montant_virement / ca_total
        else null
    end                                     as pct_virement,

    -- Marges
    marge_totale,
    marge_remboursable,
    marge_non_remboursable,
    case
        when marge_totale > 0
        then marge_remboursable / marge_totale
        else null
    end                                     as pct_marge_remboursable,

    -- TVA par taux
    tva_taux1,
    tva_taux2,
    tva_taux3,
    tva_taux4,
    tva_taux5,

    -- Retrocessions et fidelite
    ca_retrocessions,
    points_fidelite,
    remises_totales

from tresorerie_mensuelle
