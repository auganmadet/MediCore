{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['PHA_ID', '"Date"'],
        schema='STAGING',
        tags=['staging', 'history', 'incremental']
    )
}}

with source_data as (
    select * from {{ ref('raw_history') }}
    where cdc_operation != 'D'
    {% if is_incremental() %}
      and cdc_timestamp >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
),
dedup_cdc as (
    select *,
        row_number() over (
            partition by PHA_ID, "Date"
            order by cdc_timestamp desc nulls last
        ) as rn
    from source_data
)
select PHA_ID, "Date", EspeceFRF, ChequeFRF, CB, Centre, Differe_Positif,
       nb_De_Factures, nb_De_Subro, TVA_1, TVA_2, TVA_3, TVA_4, TVA_5,
       Marge_Rembt, Marge_NRembt, Remise_EnCompte, Remise_EnLigne,EnCompte_Positif,
       Mutuelle, EspeceEUR, ChequeEUR, Virement, SubroPartAssure, Controle, PointsFidel,
       Particulier, EnCompteBL_Positif, Differe_Negatif, EnCompte_Negatif,
       EnCompteBL_Negatif, CA_Retro_1, CA_Retro_2, CA_Retro_3, CA_Retro_4, CA_Retro_5,
       DMPositif, DMNegatif, DMRetroPositif, DMRetroNegatif,cdc_timestamp as loaded_at
from dedup_cdc where rn = 1
