{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['pharmacie_sk', 'operateur', 'date_vente', 'heure_vente'],
        schema='MARTS',
        tags=['marts', 'fact', 'operateur', 'high_volume', 'incremental']
    )
}}

with ventes_operateur as (
    select
        m.PHA_ID,
        m.ORD_OPERATEUR,
        m.FAC_DATE::date                as date_vente,
        extract(hour from m.FAC_HEURE)  as heure_vente,
        m.FAC_QUANTITE,
        m.FAC_PVHT,
        m.FAC_PVTTC,
        m.FAC_PAHT,
        m.FAC_CODEREMBT,
        ph.pharmacie_sk,
        m.loaded_at
    from {{ ref('stg_mediprix_factures') }} m
    inner join {{ ref('dim_pharmacie') }} ph
        on m.PHA_ID = ph.PHA_ID
    where m.ORD_OPERATEUR is not null
    {% if is_incremental() %}
      and m.loaded_at >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
)

select
    pharmacie_sk,
    ORD_OPERATEUR                                           as operateur,
    date_vente,
    heure_vente,
    sum(FAC_QUANTITE)                                       as quantite_vendue,
    sum(FAC_PVHT)                                           as ca_ht,
    sum(FAC_PVTTC)                                          as ca_ttc,
    sum(FAC_PAHT)                                           as cout_achat_ht,
    count(*)                                                as nb_lignes,
    count(case when FAC_CODEREMBT is not null
               and FAC_CODEREMBT != '' then 1 end)          as nb_lignes_remboursables,
    max(loaded_at)                                          as loaded_at
from ventes_operateur
group by pharmacie_sk, ORD_OPERATEUR, date_vente, heure_vente
