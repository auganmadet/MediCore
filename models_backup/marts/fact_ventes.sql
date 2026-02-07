{{
    config(
        materialized='incremental',
        schema='MART',
        unique_key=['pharmacie_sk', 'PRD_ID', 'FAC_DATE'],
        tags=[marts, 'fact', 'ventes']
    )
}}

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
        prod.produit_sk,
        o.ORD_CLIENT_AGE_MONTHS,
        o.ORD_CLIENT_SEX,
        row_number() over (
            partition by f.PHA_ID, f.PRD_ID, f.FAC_DATE::date
            order by f.cdc_timestamp desc
        ) as rn
    from {{ ref('stg_factures') }} f
    left join {{ ref('dim_pharmacie') }} ph 
        on f.PHA_ID = ph.PHA_ID 
        and f.FAC_DATE::date >= ph.valid_from 
        and f.FAC_DATE::date < ph.valid_to
    left join {{ ref('dim_produit') }} prod 
        on f.PHA_ID = prod.PHA_ID and f.PRD_ID = prod.PRD_ID
    left join {{ ref('stg_orders') }} o 
        on f.PHA_ID = o.PHA_ID and f.FAC_ID = o.FAC_ID
    where f.cdc_operation != 'D'
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
    count(*) as nb_lignes
from ventes_enriched 
where rn = 1
{% if is_incremental() %}
    and date_vente >= (select max(date_vente) from {{ this }})
{% endif %}
group by 1,2,3,10,11

