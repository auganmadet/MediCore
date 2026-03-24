-- Test singular : vérifie les KPIs calculés dans mart_kpi_ruptures.
-- - taux_rupture_demande = nb_lignes_manquantes / (nb_lignes_vendues + nb_lignes_manquantes)
-- - ca_estime_perdu et marge_estimee_perdue dépendent de prix_public_moyen (non recalculable ici)
-- On vérifie uniquement taux_rupture_demande (formule déterministe).

select
    pharmacie_sk, produit_sk, mois,
    taux_rupture_demande,
    nb_lignes_manquantes::float / (nb_lignes_vendues + nb_lignes_manquantes) as taux_attendu,
    abs(taux_rupture_demande - nb_lignes_manquantes::float / (nb_lignes_vendues + nb_lignes_manquantes)) as ecart
from {{ ref('mart_kpi_ruptures') }}
where (nb_lignes_vendues + nb_lignes_manquantes) > 0
  and taux_rupture_demande is not null
  and abs(taux_rupture_demande - nb_lignes_manquantes::float / (nb_lignes_vendues + nb_lignes_manquantes)) > 0.001
