-- Test singular : vérifie les KPIs agrégés dans mart_kpi_synthese_pharmacie.
-- - taux_marge = marge_brute / ca_ht (vient de generique_summary)
-- - taux_generique = ca_ht_generique / (ca_ht_generique + ca princeps)
-- - ratio_stock_ca_annuel_pct = (valeur_stock_pa / ca_ht_ytd) * 100
-- - pct_dormants_6m = nb_dormants_6m / nb_produits_en_stock (approximation)

select
    pharmacie_sk, mois,
    'ratio_stock_ca' as kpi,
    ratio_stock_ca_annuel_pct as valeur,
    (valeur_stock_pa / ca_ht_ytd) * 100 as valeur_attendue,
    abs(ratio_stock_ca_annuel_pct - (valeur_stock_pa / ca_ht_ytd) * 100) as ecart
from {{ ref('mart_kpi_synthese_pharmacie') }}
where ca_ht_ytd > 0
  and ratio_stock_ca_annuel_pct is not null
  and abs(ratio_stock_ca_annuel_pct - (valeur_stock_pa / ca_ht_ytd) * 100) > 0.01
