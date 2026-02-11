{{
  config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['pharmacie_sk', 'produit_sk', 'date_prix'],
    schema='MARTS',
    tags=['marts', 'fact', 'prix_journalier', 'high_volume', 'incremental']
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
        d.loaded_at,
        row_number() over (
          partition by d.PHA_ID, d.PRD_ID, d.DBD_DATE
          order by d.loaded_at desc
        ) as rn
    from {{ ref('stg_daybyday') }} d
    inner join {{ ref('dim_pharmacie') }} ph
      on d.PHA_ID = ph.PHA_ID
    inner join {{ ref('dim_produit') }} prod
      on d.PHA_ID = prod.PHA_ID
      and d.PRD_ID = prod.PRD_ID
    {% if is_incremental() %}
    where d.loaded_at >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
)

select
    pharmacie_sk,
    produit_sk,
    date_prix,
    DBD_PRIXTARIF  as prix_tarif,
    DBD_PRIXPUBLIC as prix_public,
    DBD_PAMP       as prix_achat_moyen_pondere,
    DBD_PANET      as prix_achat_net,
    DBD_PRIXPUBLIC - DBD_PANET as marge_brute_unitaire,
    case
        when DBD_PRIXPUBLIC != 0
        then (DBD_PRIXPUBLIC - DBD_PANET) / DBD_PRIXPUBLIC
        else null
    end as taux_marge_unitaire,
    loaded_at
from prix
where rn = 1
