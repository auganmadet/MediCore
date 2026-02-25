{{
  config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key=['pharmacie_sk', 'produit_sk', 'fournisseur_sk', 'date_commande', 'commande_id'],
    schema='MARTS',
    tags=['marts', 'fact', 'commandes', 'high_volume', 'incremental']
  )
}}
{{ guard_full_refresh() }}

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
        coalesce(prod.produit_sk, md5('-1' || '-' || '-1')) as produit_sk,
        coalesce(f.fournisseur_sk, md5('-1' || '-' || '-1')) as fournisseur_sk,
        c.loaded_at
    from {{ ref('stg_commandes') }} c
    inner join {{ ref('dim_pharmacie') }} ph
      on c.PHA_ID = ph.PHA_ID
    left join {{ ref('dim_produit') }} prod
      on c.PHA_ID = prod.PHA_ID
      and c.PRD_ID = prod.PRD_ID
    left join {{ ref('dim_fournisseur') }} f
      on c.PHA_ID = f.PHA_ID
      and c.FOU_ID = f.FOU_ID
    {% if is_incremental() %}
    where c.loaded_at >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
)

select
    pharmacie_sk,
    produit_sk,
    fournisseur_sk,
    COM_DATE       as date_commande,
    COM_GROI       as commande_id,
    sum(COM_QUANTITE)      as quantite_commandee,
    sum(COM_PAHTNET)       as montant_pahtnet,
    avg(COM_TAUXREMISE)    as remise_moyenne,
    max(loaded_at) as loaded_at
from commandes_enriched
group by pharmacie_sk, produit_sk, fournisseur_sk, COM_DATE, COM_GROI
