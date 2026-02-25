{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'kpi', 'qualite', 'monitoring']
    )
}}

with derniere_sync as (
    select
        l.PHA_ID,
        l.DATE_SYNC,
        ph.pharmacie_sk,
        ph.PHA_NOM,
        datediff('hour', l.DATE_SYNC, current_timestamp())  as heures_depuis_sync,
        case
            when datediff('hour', l.DATE_SYNC, current_timestamp()) <= 24
                then 'OK'
            when datediff('hour', l.DATE_SYNC, current_timestamp()) <= 48
                then 'ALERTE'
            else 'CRITIQUE'
        end                                                  as statut_fraicheur
    from {{ ref('stg_log') }} l
    inner join {{ ref('dim_pharmacie') }} ph
        on l.PHA_ID = ph.PHA_ID
),

erreurs_recentes as (
    select
        count(*)                                             as nb_erreurs_total,
        count(distinct code_erreur)                          as nb_codes_erreur_distincts,
        max(date_erreur)                                     as derniere_erreur
    from {{ ref('stg_pharmacies_erreur') }}
),

stats_globales as (
    select
        count(*)                                             as nb_pharmacies_total,
        count(case when statut_fraicheur = 'OK' then 1 end) as nb_pharmacies_ok,
        count(case when statut_fraicheur = 'ALERTE' then 1 end)
                                                             as nb_pharmacies_alerte,
        count(case when statut_fraicheur = 'CRITIQUE' then 1 end)
                                                             as nb_pharmacies_critique
    from derniere_sync
)

select
    s.pharmacie_sk,
    s.PHA_NOM,
    s.DATE_SYNC                                              as derniere_sync,
    s.heures_depuis_sync,
    s.statut_fraicheur,
    g.nb_pharmacies_total,
    g.nb_pharmacies_ok,
    g.nb_pharmacies_alerte,
    g.nb_pharmacies_critique,
    case
        when g.nb_pharmacies_total > 0
        then g.nb_pharmacies_ok::float / g.nb_pharmacies_total
        else null
    end                                                      as taux_pharmacies_ok,
    e.nb_erreurs_total,
    e.nb_codes_erreur_distincts,
    e.derniere_erreur
from derniere_sync s
cross join stats_globales g
cross join erreurs_recentes e
