{{
    config(
        materialized='incremental',
        unique_key=['pharmacie_sk', 'fou_nom', 'mois'],
        incremental_strategy='merge',
        schema='MARTS',
        tags=['marts', 'kpi', 'ecoulement', 'agrege']
    )
}}

-- Écoulement agrégé par fournisseur (pondéré par quantités commandées)
-- Utilisé par : D9 "Écoulement par fournisseur"

with ecoulement_produit as (
    select
        e.pharmacie_sk,
        f.FOU_NOM                                           as fou_nom,
        e.mois,
        e.quantite_commandee,
        e.quantite_vendue
    from {{ ref('mart_kpi_ecoulement') }} e
    inner join {{ ref('dim_produit') }} p
        on e.produit_sk = p.produit_sk
    inner join {{ ref('dim_fournisseur') }} f
        on p.FOU_ID = f.FOU_ID
        and p.PHA_ID = f.PHA_ID
    where f.FOU_NOM is not null
    {% if is_incremental() %}
    and e.mois >= dateadd('month', -2, current_date())
    {% endif %}
)

select
    pharmacie_sk,
    fou_nom,
    mois,
    sum(quantite_commandee)                                 as quantite_commandee,
    sum(quantite_vendue)                                    as quantite_vendue,
    case
        when sum(quantite_commandee) > 0
        then sum(quantite_vendue)::float / sum(quantite_commandee)
        else null
    end                                                     as taux_ecoulement
from ecoulement_produit
group by pharmacie_sk, fou_nom, mois
