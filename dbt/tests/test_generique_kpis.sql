-- Test singular : vérifie les KPIs calculés dans mart_kpi_generique.
-- - taux_generique_pharmacie = ca_ht_generique / ca_ht_total
-- - pdm_labo = ca_ht / ca_ht_total

select
    pharmacie_sk, mois, FOU_ID,
    'taux_generique_pharmacie' as kpi,
    taux_generique_pharmacie as valeur,
    ca_ht_generique / ca_ht_total as valeur_attendue,
    abs(taux_generique_pharmacie - ca_ht_generique / ca_ht_total) as ecart
from {{ ref('mart_kpi_generique') }}
where ca_ht_total > 0
  and taux_generique_pharmacie is not null
  and abs(taux_generique_pharmacie - ca_ht_generique / ca_ht_total) > 0.001

union all

select
    pharmacie_sk, mois, FOU_ID,
    'pdm_labo',
    pdm_labo,
    ca_ht / ca_ht_total,
    abs(pdm_labo - ca_ht / ca_ht_total)
from {{ ref('mart_kpi_generique') }}
where ca_ht_total > 0
  and pdm_labo is not null
  and abs(pdm_labo - ca_ht / ca_ht_total) > 0.001
