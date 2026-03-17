{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'mois', 'type_produit'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'generique', 'agrege']
    )
}}

-- Marge agrégée générique vs princeps
-- Utilisé par : D13 "Marge générique vs princeps"

select
    pharmacie_sk,
    mois,
    case
        when is_generique then 'Générique'
        else 'Princeps'
    end                                                     as type_produit,
    sum(ca_ht)                                              as ca_ht,
    sum(marge_brute)                                        as marge_brute,
    case
        when sum(ca_ht) > 0
        then sum(marge_brute) / sum(ca_ht)
        else null
    end                                                     as taux_marge
from {{ ref('mart_kpi_generique') }}
{% if is_incremental() %}
where mois >= dateadd('month', -2, current_date())
{% endif %}
group by pharmacie_sk, mois, type_produit
