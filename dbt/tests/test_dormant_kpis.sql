-- Test singular : vérifie les KPIs calculés dans mart_kpi_dormant.
-- - is_dormant_6m doit être cohérent avec jours_sans_vente >= 180
-- - marge_latente_bloquee = valeur_stock_pv - valeur_stock_pa
-- - statut_dormant cohérent avec jours_sans_vente

-- Vérifie cohérence is_dormant_6m / jours_sans_vente
select
    pharmacie_sk, produit_sk,
    'is_dormant_6m_incoherent' as kpi,
    jours_sans_vente,
    is_dormant_6m
from {{ ref('mart_kpi_dormant') }}
where (is_dormant_6m = true and jours_sans_vente < 180 and derniere_vente is not null)
   or (is_dormant_6m = false and (jours_sans_vente >= 180 or derniere_vente is null))

union all

-- Vérifie marge_latente_bloquee = pv - pa
select
    pharmacie_sk, produit_sk,
    'marge_latente_bloquee_ecart',
    marge_latente_bloquee,
    null
from {{ ref('mart_kpi_dormant') }}
where valeur_stock_pv is not null
  and valeur_stock_pa is not null
  and abs(marge_latente_bloquee - (coalesce(valeur_stock_pv, 0) - coalesce(valeur_stock_pa, 0))) > 0.01

union all

-- Vérifie cohérence statut_dormant / jours_sans_vente
select
    pharmacie_sk, produit_sk,
    'statut_dormant_incoherent',
    jours_sans_vente,
    null
from {{ ref('mart_kpi_dormant') }}
where (statut_dormant = 'ACTIF' and jours_sans_vente >= 90)
   or (statut_dormant = 'DORMANT_3M' and (jours_sans_vente < 90 or jours_sans_vente >= 180))
   or (statut_dormant = 'DORMANT_6M' and (jours_sans_vente < 180 or jours_sans_vente >= 365))
   or (statut_dormant = 'DORMANT_12M' and jours_sans_vente < 365)
