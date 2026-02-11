{{
    config(
        materialized='table',
        schema='MARTS',
        tags=['marts', 'dim', 'produit']
    )
}}

with enriched_products as (
    select
        p.PHA_ID,
        p.PRD_ID,
        p.PRD_NOM,
        p.PRD_EAN13,
        p.PRD_CODEREMBT,
        p.PRD_CODEACTE,
        p.PRD_TVA,
        p.FOU_ID,
        p.PRD_STOCK,
        e.EAN_13 as primary_ean13,
        l.LPP_CODE,
        l.LPP_ACTE_NOM,
        p.loaded_at,
        row_number() over (
            partition by p.PHA_ID, p.PRD_ID
            order by p.loaded_at desc
        ) as rn
    from {{ ref('stg_produits') }} p
    left join {{ ref('stg_ean13') }} e
        on p.PHA_ID = e.PHA_ID and p.PRD_ID = e.PRD_ID
    left join {{ ref('stg_lppr') }} l
        on p.PHA_ID = l.PHA_ID and p.PRD_ID = l.PRD_ID
    left join {{ ref('stg_produits_negatifs') }} neg
        on p.PRD_ID = neg.PRD_ID
    where neg.PRD_ID is null
)

select
    md5(PHA_ID::string || '-' || PRD_ID::string) as produit_sk,
    PHA_ID,
    PRD_ID,
    PRD_NOM,
    coalesce(primary_ean13, PRD_EAN13) as EAN13,
    PRD_CODEREMBT,
    PRD_CODEACTE,
    PRD_TVA,
    FOU_ID,
    PRD_STOCK,
    LPP_CODE,
    LPP_ACTE_NOM
from enriched_products
where rn = 1
