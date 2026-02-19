{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['pharmacie_sk', 'produit_sk', 'date_vente', 'ORD_CLIENT_AGE_MONTHS', 'ORD_CLIENT_SEX'],
        schema='MARTS',
        tags=['marts', 'fact', 'ventes', 'high_volume', 'incremental']
    )
}}
{{ guard_full_refresh() }}

with ventes_enriched as (
    select
        f.PHA_ID,
        f.PRD_ID,
        f.FAC_DATE::date as date_vente,
        f.FAC_QUANTITE,
        f.FAC_PVHT as ca_ht,
        f.FAC_PVTTC as ca_ttc,
        f.FAC_TVA,
        f.FAC_REMISE,
        f.FAC_CODEREMBT,
        ph.pharmacie_sk,
        coalesce(prod.produit_sk, md5('-1' || '-' || '-1')) as produit_sk,
        o.ORD_CLIENT_AGE_MONTHS,
        o.ORD_CLIENT_SEX,
        f.loaded_at
    from {{ ref('stg_factures') }} f
    inner join {{ ref('dim_pharmacie') }} ph
        on f.PHA_ID = ph.PHA_ID
    left join {{ ref('dim_produit') }} prod
        on f.PHA_ID = prod.PHA_ID and f.PRD_ID = prod.PRD_ID
    left join {{ ref('stg_orders') }} o
        on f.PHA_ID = o.PHA_ID and f.FAC_ID = o.FAC_ID
    {% if is_incremental() %}
    where f.loaded_at >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
)

select
    pharmacie_sk,
    produit_sk,
    date_vente,
    sum(FAC_QUANTITE) as quantite_vendue,
    sum(ca_ht) as ca_ht,
    sum(ca_ttc) as ca_ttc,
    avg(FAC_TVA) as tva_moyenne,
    max(FAC_REMISE) as remise_max,
    ORD_CLIENT_AGE_MONTHS,
    ORD_CLIENT_SEX,
    count(*) as nb_lignes,
    max(loaded_at) as loaded_at
from ventes_enriched
group by pharmacie_sk, produit_sk, date_vente, ORD_CLIENT_AGE_MONTHS, ORD_CLIENT_SEX
