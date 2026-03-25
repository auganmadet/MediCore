-- Test singular : vérifie les KPIs calculés dans mart_kpi_stock_valorisation.
-- - couverture_stock_jours = stock_fin_mois * 30.0 / quantite_vendue
-- - marge_latente_moyenne = valeur_stock_pv_moyenne - valeur_stock_pa_moyenne (non recalculable ici)
-- On vérifie uniquement couverture_stock_jours.

select
    pharmacie_sk, produit_sk, mois,
    couverture_stock_jours,
    stock_fin_mois * 30.0 / quantite_vendue as couverture_attendue,
    abs(couverture_stock_jours - stock_fin_mois * 30.0 / quantite_vendue) as ecart
from {{ ref('mart_kpi_stock_valorisation') }}
where quantite_vendue > 0
  and couverture_stock_jours is not null
  and abs(couverture_stock_jours - stock_fin_mois * 30.0 / quantite_vendue) > 0.01
