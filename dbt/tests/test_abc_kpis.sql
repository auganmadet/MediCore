-- Test singular : vérifie les KPIs calculés dans mart_kpi_abc.
-- - pct_ca = ca_ht / ca_total
-- - classe_abc : A si pct_ca_cumule <= 0.80, B si <= 0.95, C sinon

select
    pharmacie_sk, produit_sk, mois,
    'pct_ca' as kpi,
    pct_ca as valeur,
    ca_ht / ca_total as valeur_attendue,
    abs(pct_ca - ca_ht / ca_total) as ecart
from {{ ref('mart_kpi_abc') }}
where ca_total > 0
  and pct_ca is not null
  and abs(pct_ca - ca_ht / ca_total) > 0.001

union all

-- Vérifie la cohérence de classe_abc avec pct_ca_cumule
select
    pharmacie_sk, produit_sk, mois,
    'classe_abc_coherence',
    null,
    null,
    null
from {{ ref('mart_kpi_abc') }}
where (classe_abc = 'A' and pct_ca_cumule > 0.80)
   or (classe_abc = 'B' and (pct_ca_cumule <= 0.80 or pct_ca_cumule > 0.95))
   or (classe_abc = 'C' and pct_ca_cumule <= 0.95)
