{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'univers'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'marge', 'agrege']
    )
}}

-- Marge agrégée par univers (RX, OTC, PARA)
-- Utilisé par : D4 "Taux de marge par univers"

with marge_univers as (
    select
        m.pharmacie_sk,
        p.univers,
        sum(m.marge_brute)                                  as marge_brute,
        sum(m.ca_ht)                                        as ca_ht,
        sum(m.quantite_vendue)                              as quantite_vendue,
        case
            when sum(m.ca_ht) > 0
            then sum(m.marge_brute) / sum(m.ca_ht) * 100
            else null
        end                                                 as taux_marge_pct
    from {{ ref('mart_kpi_marge') }} m
    inner join {{ ref('dim_produit') }} p
        on m.produit_sk = p.produit_sk
    where p.univers is not null
    {% if is_incremental() %}
    and m.date_jour >= dateadd('month', -2, current_date())
    {% endif %}
    group by m.pharmacie_sk, p.univers
)

select * from marge_univers
