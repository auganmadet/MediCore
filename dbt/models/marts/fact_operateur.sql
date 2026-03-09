{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['pharmacie_sk', 'operateur', 'date_vente', 'heure_vente'],
        schema='MARTS',
        tags=['marts', 'fact', 'operateur', 'high_volume', 'incremental']
    )
}}
{{ guard_full_refresh() }}

with ventes_operateur as (
    select
        m.PHA_ID,
        m.FAC_ID,
        m.ORD_OPERATEUR,
        try_to_date(m.FAC_DATE)         as date_vente,
        extract(hour from try_to_time(m.FAC_HEURE))  as heure_vente,
        m.FAC_QUANTITE,
        m.FAC_PVHT,
        m.FAC_PVTTC,
        m.FAC_PAHT,
        m.FAC_CODEREMBT,
        coalesce(ph.pharmacie_sk, md5('-1')) as pharmacie_sk,
        -- Jointure avec stg_orders pour récupérer l'identifiant client
        o.ORD_CLI_TI,
        m.loaded_at
    from {{ ref('stg_mediprix_factures') }} m
    left join {{ ref('dim_pharmacie') }} ph
        on m.PHA_ID = ph.PHA_ID
    left join {{ ref('stg_orders') }} o
        on m.PHA_ID = o.PHA_ID
        and m.FAC_ID = o.FAC_ID
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
    count(case when FAC_CODEREMBT is not null then 1 end)   as nb_lignes_remboursables,
    -- KPI: Nombre de clients distincts servis
    count(distinct ORD_CLI_TI)                              as nb_clients_distincts,
    max(loaded_at)                                          as loaded_at
from ventes_operateur
group by pharmacie_sk, ORD_OPERATEUR, date_vente, heure_vente
