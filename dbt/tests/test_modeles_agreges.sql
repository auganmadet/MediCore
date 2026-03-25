-- Test singular : vérifie les 6 modèles agrégés.
-- Chaque modèle agrégé doit avoir des totaux cohérents avec sa table source.

-- mart_kpi_marge_par_produit : SUM(marge_brute) par produit doit correspondre
-- à SUM(marge_brute) dans mart_kpi_marge pour le même produit
with marge_source as (
    select pharmacie_sk, produit_sk, sum(marge_brute) as marge_source
    from {{ ref('mart_kpi_marge') }}
    group by pharmacie_sk, produit_sk
),
marge_agrege as (
    select pharmacie_sk, produit_sk, marge_brute as marge_agrege
    from {{ ref('mart_kpi_marge_par_produit') }}
)
select
    s.pharmacie_sk, s.produit_sk,
    'marge_par_produit' as test,
    s.marge_source, a.marge_agrege,
    abs(s.marge_source - a.marge_agrege) as ecart
from marge_source s
inner join marge_agrege a
    on s.pharmacie_sk = a.pharmacie_sk and s.produit_sk = a.produit_sk
where abs(s.marge_source - a.marge_agrege) > 0.01

union all

-- mart_kpi_ecoulement_par_fournisseur : taux_ecoulement pondéré
-- = SUM(qte_vendue) / SUM(qte_commandee)
select
    pharmacie_sk, fou_nom,
    'ecoulement_par_fournisseur',
    taux_ecoulement,
    quantite_vendue::float / quantite_commandee,
    abs(taux_ecoulement - quantite_vendue::float / quantite_commandee)
from {{ ref('mart_kpi_ecoulement_par_fournisseur') }}
where quantite_commandee > 0
  and taux_ecoulement is not null
  and abs(taux_ecoulement - quantite_vendue::float / quantite_commandee) > 0.001

union all

-- mart_kpi_generique_marge : taux_marge = SUM(marge) / SUM(ca)
select
    pharmacie_sk, type_produit,
    'generique_marge',
    taux_marge,
    marge_brute / ca_ht,
    abs(taux_marge - marge_brute / ca_ht)
from {{ ref('mart_kpi_generique_marge') }}
where ca_ht > 0
  and taux_marge is not null
  and abs(taux_marge - marge_brute / ca_ht) > 0.001

union all

-- mart_kpi_marge_par_univers : taux_marge_pct = SUM(marge) / SUM(ca) * 100
select
    pharmacie_sk, univers,
    'marge_par_univers',
    taux_marge_pct,
    marge_brute / ca_ht * 100,
    abs(taux_marge_pct - marge_brute / ca_ht * 100)
from {{ ref('mart_kpi_marge_par_univers') }}
where ca_ht > 0
  and taux_marge_pct is not null
  and abs(taux_marge_pct - marge_brute / ca_ht * 100) > 0.01
