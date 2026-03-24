-- Test singular : le CA_TOTAL dans mart_kpi_tresorerie (mensuel) doit correspondre
-- à la somme des ca_total_jour dans fact_tresorerie (quotidien).
-- Un écart > 0.01€ signale un bug dans l'agrégation.
-- Si cette requête retourne des lignes, le test échoue.

-- - fact_tresorerie : une ligne par pharmacie × jour (ca_total_jour)
-- - mart_kpi_tresorerie : une ligne par pharmacie × mois (ca_total = SUM quotidien)

with tresorerie as (
    select
        pharmacie_sk,
        mois,
        ca_total
    from {{ ref('mart_kpi_tresorerie') }}
),

fact as (
    select
        pharmacie_sk,
        date_trunc('month', date_jour) as mois,
        sum(ca_total_jour) as ca_total_fact
    from {{ ref('fact_tresorerie') }}
    group by pharmacie_sk, date_trunc('month', date_jour)
)

select
    t.pharmacie_sk,
    t.mois,
    t.ca_total as ca_kpi,
    f.ca_total_fact as ca_fact,
    abs(t.ca_total - f.ca_total_fact) as ecart
from tresorerie t
inner join fact f
    on t.pharmacie_sk = f.pharmacie_sk
    and t.mois = f.mois
where abs(t.ca_total - f.ca_total_fact) > 0.01
