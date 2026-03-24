-- Test singular : vérifie les KPIs calculés dans mart_kpi_univers.
-- - pct_ca_univers = ca_ht / ca_ht_total
-- - pct_marge_univers = marge_brute / marge_brute_total

select
    pharmacie_sk, mois, univers,
    'pct_ca_univers' as kpi,
    pct_ca_univers as valeur,
    ca_ht / ca_ht_total as valeur_attendue,
    abs(pct_ca_univers - ca_ht / ca_ht_total) as ecart
from {{ ref('mart_kpi_univers') }}
where ca_ht_total > 0
  and pct_ca_univers is not null
  and abs(pct_ca_univers - ca_ht / ca_ht_total) > 0.001

union all

select
    pharmacie_sk, mois, univers,
    'pct_marge_univers',
    pct_marge_univers,
    marge_brute / marge_brute_total,
    abs(pct_marge_univers - marge_brute / marge_brute_total)
from {{ ref('mart_kpi_univers') }}
where marge_brute_total > 0
  and pct_marge_univers is not null
  and abs(pct_marge_univers - marge_brute / marge_brute_total) > 0.001
