{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'produit_sk', 'mois'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'ruptures', 'agrege']
    )
}}

-- Ruptures enrichies avec nom produit
-- Utilisé par : D8 "Top 10 produits en rupture" + "Jours de rupture par produit"

select
    r.pharmacie_sk,
    r.produit_sk,
    p.PRD_NOM,
    r.mois,
    r.nb_boites_manquantes,
    r.nb_jours_rupture,
    r.nb_clients_impactes,
    r.ca_estime_perdu,
    r.marge_estimee_perdue,
    r.taux_rupture_demande
from {{ ref('mart_kpi_ruptures') }} r
inner join {{ ref('dim_produit') }} p
    on r.produit_sk = p.produit_sk
{% if is_incremental() %}
where r.mois >= dateadd('month', -2, current_date())
{% endif %}
