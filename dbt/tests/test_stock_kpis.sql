-- Test singular : vérifie les KPIs calculés dans mart_kpi_stock.
-- - rotation_stock = quantite_vendue / stock_moyen
-- - taux_rupture_stock = nb_jours_rupture / nb_jours_mouvement
-- Bug corrigé : v.m → v.mois dans mart_kpi_stock.sql (fichier tronqué).

select
    pharmacie_sk, produit_sk, mois,
    'rotation_stock' as kpi,
    rotation_stock as valeur,
    quantite_vendue::float / stock_moyen as valeur_attendue,
    abs(rotation_stock - quantite_vendue::float / stock_moyen) as ecart
from {{ ref('mart_kpi_stock') }}
where stock_moyen > 0
  and rotation_stock is not null
  and abs(rotation_stock - quantite_vendue::float / stock_moyen) > 0.001

union all

select
    pharmacie_sk, produit_sk, mois,
    'taux_rupture_stock',
    taux_rupture_stock,
    nb_jours_rupture::float / nb_jours_mouvement,
    abs(taux_rupture_stock - nb_jours_rupture::float / nb_jours_mouvement)
from {{ ref('mart_kpi_stock') }}
where nb_jours_mouvement > 0
  and taux_rupture_stock is not null
  and abs(taux_rupture_stock - nb_jours_rupture::float / nb_jours_mouvement) > 0.001
