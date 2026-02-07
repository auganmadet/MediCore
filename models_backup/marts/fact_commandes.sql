{{ 
  config(
    materialized='table',
    schema='MARTS',
    tags=[marts, 'fact', 'commandes']
  ) 
}}

with commandes_enriched as (
    select
        c.PHA_ID,
        c.COM_GROI,
        c.PRD_ID,
        c.COM_DATE,
        c.FOU_ID,
        c.COM_QUANTITE,
        c.COM_PAHTNET,
        c.COM_TAUXREMISE,
        ph.pharmacie_sk,
        prod.produit_sk,
        f.fournisseur_sk,
        row_number() over (
          partition by c.PHA_ID, c.COM_GROI, c.PRD_ID
          order by c.loaded_at desc
        ) as rn
    from {{ ref('stg_commandes') }} c
    left join {{ ref('dim_pharmacie') }} ph
      on c.PHA_ID = ph.PHA_ID
      and c.COM_DATE between ph.valid_from and ph.valid_to
    left join {{ ref('dim_produit') }} prod
      on c.PHA_ID = prod.PHA_ID
      and c.PRD_ID  = prod.PRD_ID
    left join {{ ref('dim_fournisseur') }} f
      on c.PHA_ID = f.PHA_ID
      and c.FOU_ID = f.FOU_ID
)

select
    pharmacie_sk,
    produit_sk,
    fournisseur_sk,
    COM_DATE       as date_commande,
    COM_GROI       as commande_id,
    sum(COM_QUANTITE)      as quantite_commandee,
    sum(COM_PAHTNET)       as montant_pahtnet,
    avg(COM_TAUXREMISE)    as remise_moyenne
from commandes_enriched
where rn = 1
group by 1,2,3,4,5

