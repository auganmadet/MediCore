-- Test singular : vérifie les KPIs calculés dans mart_kpi_ca_evolution.
-- - evolution_ca_ht_vs_a1 = (ca_ht - ca_ht_a1) / ca_ht_a1
-- - evolution_ytd_vs_a1 = (ca_ht_ytd - ca_ht_ytd_a1) / ca_ht_ytd_a1

select
    pharmacie_sk, mois,
    'evolution_ca_ht_vs_a1' as kpi,
    evolution_ca_ht_vs_a1 as valeur,
    (ca_ht - ca_ht_a1) / ca_ht_a1 as valeur_attendue,
    abs(evolution_ca_ht_vs_a1 - (ca_ht - ca_ht_a1) / ca_ht_a1) as ecart
from {{ ref('mart_kpi_ca_evolution') }}
where ca_ht_a1 > 0
  and evolution_ca_ht_vs_a1 is not null
  and abs(evolution_ca_ht_vs_a1 - (ca_ht - ca_ht_a1) / ca_ht_a1) > 0.001

union all

select
    pharmacie_sk, mois,
    'evolution_ytd_vs_a1',
    evolution_ytd_vs_a1,
    (ca_ht_ytd - ca_ht_ytd_a1) / ca_ht_ytd_a1,
    abs(evolution_ytd_vs_a1 - (ca_ht_ytd - ca_ht_ytd_a1) / ca_ht_ytd_a1)
from {{ ref('mart_kpi_ca_evolution') }}
where ca_ht_ytd_a1 > 0
  and evolution_ytd_vs_a1 is not null
  and abs(evolution_ytd_vs_a1 - (ca_ht_ytd - ca_ht_ytd_a1) / ca_ht_ytd_a1) > 0.001
