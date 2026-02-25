{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'operateur']
    )
}}

with operateur_mensuel as (
    select
        pharmacie_sk,
        operateur,
        date_trunc('month', date_vente)                     as mois,
        sum(quantite_vendue)                                as quantite_vendue,
        sum(ca_ht)                                          as ca_ht,
        sum(ca_ttc)                                         as ca_ttc,
        sum(cout_achat_ht)                                  as cout_achat_ht,
        sum(nb_lignes)                                      as nb_lignes,
        sum(nb_lignes_remboursables)                        as nb_lignes_remboursables,
        count(distinct date_vente)                          as nb_jours_activite
    from {{ ref('fact_operateur') }}
    group by pharmacie_sk, operateur, date_trunc('month', date_vente)
),

heures_pic as (
    select
        pharmacie_sk,
        operateur,
        date_trunc('month', date_vente)                     as mois,
        max_by(heure_vente, ca_ttc_heure)                   as heure_pic_ca
    from (
        select
            pharmacie_sk,
            operateur,
            date_vente,
            heure_vente,
            sum(ca_ttc) as ca_ttc_heure
        from {{ ref('fact_operateur') }}
        group by pharmacie_sk, operateur, date_vente, heure_vente
    )
    group by pharmacie_sk, operateur, date_trunc('month', date_vente)
)

select
    o.pharmacie_sk,
    o.operateur,
    o.mois,

    -- Volumes
    o.ca_ht,
    o.ca_ttc,
    o.quantite_vendue,
    o.nb_lignes,
    o.nb_jours_activite,

    -- Panier moyen
    case
        when o.nb_lignes > 0
        then o.ca_ttc / o.nb_lignes
        else null
    end                                                     as panier_moyen,

    -- Productivite journaliere
    case
        when o.nb_jours_activite > 0
        then o.ca_ttc / o.nb_jours_activite
        else null
    end                                                     as ca_moyen_par_jour,

    -- Marge operateur
    o.ca_ht - o.cout_achat_ht                               as marge_brute,
    case
        when o.ca_ht > 0
        then (o.ca_ht - o.cout_achat_ht) / o.ca_ht
        else null
    end                                                     as taux_marge,

    -- Mix rembourse / libre
    case
        when o.nb_lignes > 0
        then o.nb_lignes_remboursables::float / o.nb_lignes
        else null
    end                                                     as pct_lignes_remboursables,

    -- Heure de pic d'activite
    h.heure_pic_ca

from operateur_mensuel o
left join heures_pic h
    on o.pharmacie_sk = h.pharmacie_sk
    and o.operateur = h.operateur
    and o.mois = h.mois
