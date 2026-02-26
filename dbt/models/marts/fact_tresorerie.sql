{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key=['pharmacie_sk', 'date_jour'],
        schema='MARTS',
        tags=['marts', 'fact', 'tresorerie', 'incremental']
    )
}}

with tresorerie_enriched as (
    select
        h.PHA_ID,
        h."Date"::date                  as date_jour,
        h.EspeceEUR,
        h.ChequeEUR,
        h.CB,
        h.Mutuelle,
        h.Virement,
        h.Centre,
        h.SubroPartAssure,
        h.Differe_Positif,
        h.Differe_Negatif,
        h.EnCompte_Positif,
        h.EnCompte_Negatif,
        h.nb_De_Factures,
        h.nb_De_Subro,
        h.Marge_Rembt,
        h.Marge_NRembt,
        h.Remise_EnCompte,
        h.Remise_EnLigne,
        h.TVA_1,
        h.TVA_2,
        h.TVA_3,
        h.TVA_4,
        h.TVA_5,
        h.CA_Retro_1,
        h.CA_Retro_2,
        h.CA_Retro_3,
        h.CA_Retro_4,
        h.CA_Retro_5,
        h.PointsFidel,
        coalesce(ph.pharmacie_sk, md5('-1')) as pharmacie_sk,
        h.loaded_at
    from {{ ref('stg_history') }} h
    left join {{ ref('dim_pharmacie') }} ph
        on h.PHA_ID = ph.PHA_ID
    {% if is_incremental() %}
    where h.loaded_at >= (select coalesce(max(loaded_at), '1900-01-01') from {{ this }})
    {% endif %}
)

select
    pharmacie_sk,
    date_jour,

    -- Modes de paiement
    coalesce(EspeceEUR, 0)                  as montant_especes,
    coalesce(ChequeEUR, 0)                  as montant_cheques,
    coalesce(CB, 0)                         as montant_cb,
    coalesce(Mutuelle, 0)                   as montant_mutuelle,
    coalesce(Virement, 0)                   as montant_virement,
    coalesce(Centre, 0)                     as montant_centre,
    coalesce(SubroPartAssure, 0)            as montant_subrogation,
    coalesce(Differe_Positif, 0)
        + coalesce(Differe_Negatif, 0)      as montant_differe_net,
    coalesce(EnCompte_Positif, 0)
        + coalesce(EnCompte_Negatif, 0)     as montant_en_compte_net,

    -- CA total journalier
    coalesce(EspeceEUR, 0) + coalesce(ChequeEUR, 0) + coalesce(CB, 0)
        + coalesce(Mutuelle, 0) + coalesce(Virement, 0) + coalesce(Centre, 0)
        + coalesce(SubroPartAssure, 0) + coalesce(Differe_Positif, 0)
        + coalesce(Differe_Negatif, 0) + coalesce(EnCompte_Positif, 0)
        + coalesce(EnCompte_Negatif, 0)     as ca_total_jour,

    -- Activite
    nb_De_Factures,
    nb_De_Subro,

    -- Marges
    coalesce(Marge_Rembt, 0)                as marge_remboursable,
    coalesce(Marge_NRembt, 0)               as marge_non_remboursable,
    coalesce(Marge_Rembt, 0)
        + coalesce(Marge_NRembt, 0)         as marge_totale,
    coalesce(Remise_EnCompte, 0)
        + coalesce(Remise_EnLigne, 0)       as remises_totales,

    -- TVA par taux
    coalesce(TVA_1, 0)                      as tva_taux1,
    coalesce(TVA_2, 0)                      as tva_taux2,
    coalesce(TVA_3, 0)                      as tva_taux3,
    coalesce(TVA_4, 0)                      as tva_taux4,
    coalesce(TVA_5, 0)                      as tva_taux5,

    -- Retrocessions et fidelite
    coalesce(CA_Retro_1, 0) + coalesce(CA_Retro_2, 0) + coalesce(CA_Retro_3, 0)
        + coalesce(CA_Retro_4, 0) + coalesce(CA_Retro_5, 0)
                                            as ca_retrocessions,
    coalesce(PointsFidel, 0)                as points_fidelite,

    loaded_at
from tresorerie_enriched
