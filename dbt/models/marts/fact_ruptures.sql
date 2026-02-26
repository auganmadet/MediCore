{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['pharmacie_sk', 'produit_sk', 'date_rupture'],
        schema='MARTS',
        tags=['marts', 'fact', 'ruptures', 'incremental']
    )
}}

with ruptures_enriched as (
    select
        m.PHA_ID,
        m.PRD_ID,
        m.MNQ_DATE::date                as date_rupture,
        m.EN_LIGNES,
        m.EN_BOITES,
        m.EN_CLIENTS,
        m.FAC_ID,
        coalesce(ph.pharmacie_sk, md5('-1')) as pharmacie_sk,
        coalesce(prod.produit_sk, md5('-1' || '-' || '-1')) as produit_sk,
        m.loaded_at
    from {{ ref('stg_manqhistory') }} m
    left join {{ ref('dim_pharmacie') }} ph
        on m.PHA_ID = ph.PHA_ID
    left join {{ ref('dim_produit') }} prod
        on m.PHA_ID = prod.PHA_ID
        and m.PRD_ID = prod.PRD_ID
    {% if is_incremental() %}
    where m.loaded_at >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
)

select
    pharmacie_sk,
    produit_sk,
    date_rupture,
    sum(EN_LIGNES)              as nb_lignes_manquantes,
    sum(EN_BOITES)              as nb_boites_manquantes,
    sum(EN_CLIENTS)             as nb_clients_impactes,
    count(distinct FAC_ID)      as nb_factures_impactees,
    max(loaded_at)              as loaded_at
from ruptures_enriched
group by pharmacie_sk, produit_sk, date_rupture
