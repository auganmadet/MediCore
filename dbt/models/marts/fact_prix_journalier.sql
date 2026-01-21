{{
  config(
    materialized='table',
    schema='MARTS',
    tags=[marts, 'fact', 'prix_journalier']
  )
}}

with prix as (
    select
        d.PHA_ID,
        d.PRD_ID,
        d.DBD_DATE as date_prix,
        d.DBD_PRIXTARIF,
        d.DBD_PRIXPUBLIC,
        d.DBD_PAMP,
        d.DBD_PANET,
        ph.pharmacie_sk,
        prod.produit_sk,
        row_number() over (
          partition by d.PHA_ID, d.PRD_ID, d.DBD_DATE
          order by d.loaded_at desc
        ) as rn
    from {{ ref('stg_daybyday') }} d
    left join {{ ref('dim_pharmacie') }} ph
      on d.PHA_ID = ph.PHA_ID
      and d.DBD_DATE between ph.valid_from and ph.valid_to
    left join {{ ref('dim_produit') }} prod
      on d.PHA_ID = prod.PHA_ID
      and d.PRD_ID = prod.PRD_ID
)

select
    pharmacie_sk,
    produit_sk,
    date_prix,
    DBD_PRIXTARIF  as prix_tarif,
    DBD_PRIXPUBLIC as prix_public,
    DBD_PAMP       as prix_achat_moyen_pondere,
    DBD_PANET      as prix_achat_net
from prix
where rn = 1
