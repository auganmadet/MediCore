-- Test singular : vérifie les KPIs calculés dans mart_kpi_operateur.
-- - panier_moyen = ca_ttc / nb_lignes
-- - ca_moyen_par_jour = ca_ttc / nb_jours_activite

select
    pharmacie_sk, operateur, mois,
    'panier_moyen' as kpi,
    panier_moyen as valeur,
    ca_ttc / nb_lignes as valeur_attendue,
    abs(panier_moyen - ca_ttc / nb_lignes) as ecart
from {{ ref('mart_kpi_operateur') }}
where nb_lignes > 0
  and panier_moyen is not null
  and abs(panier_moyen - ca_ttc / nb_lignes) > 0.01

union all

select
    pharmacie_sk, operateur, mois,
    'ca_moyen_par_jour',
    ca_moyen_par_jour,
    ca_ttc / nb_jours_activite,
    abs(ca_moyen_par_jour - ca_ttc / nb_jours_activite)
from {{ ref('mart_kpi_operateur') }}
where nb_jours_activite > 0
  and ca_moyen_par_jour is not null
  and abs(ca_moyen_par_jour - ca_ttc / nb_jours_activite) > 0.01
