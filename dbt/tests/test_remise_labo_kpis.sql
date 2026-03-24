-- Test singular : vérifie les KPIs calculés dans mart_kpi_remise_labo.
-- - pdm_achats_labo = montant_total / montant_total_pharmacie

select
    pharmacie_sk, fournisseur_sk, mois,
    pdm_achats_labo,
    montant_total / montant_total_pharmacie as pdm_attendue,
    abs(pdm_achats_labo - montant_total / montant_total_pharmacie) as ecart
from {{ ref('mart_kpi_remise_labo') }}
where montant_total_pharmacie > 0
  and pdm_achats_labo is not null
  and abs(pdm_achats_labo - montant_total / montant_total_pharmacie) > 0.001
