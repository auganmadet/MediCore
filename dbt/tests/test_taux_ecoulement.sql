-- Test singular : le taux_ecoulement dans mart_kpi_ecoulement doit correspondre
-- à quantite_vendue / quantite_commandee pour chaque ligne.
-- Si cette requête retourne des lignes, le test échoue.

-- - mart_kpi_ecoulement : une ligne par pharmacie × produit × mois
-- - quantite_commandee : total commandé aux fournisseurs dans le mois
-- - quantite_vendue : total vendu aux clients dans le mois
-- - taux_ecoulement = quantite_vendue / quantite_commandee

-- Le test recalcule le taux à partir des quantités et compare avec la valeur
-- stockée. Un écart > 0.1% signale un bug dans le calcul d'écoulement.
-- Le test ne vérifie que les lignes où quantite_commandee > 0 (division par zéro).

select
    pharmacie_sk,
    produit_sk,
    mois,
    quantite_commandee,
    quantite_vendue,
    taux_ecoulement,
    quantite_vendue::float / quantite_commandee as taux_ecoulement_attendu,
    abs(
        taux_ecoulement - (quantite_vendue::float / quantite_commandee)
    ) as ecart
from {{ ref('mart_kpi_ecoulement') }}
where quantite_commandee > 0
  and taux_ecoulement is not null
  and abs(
      taux_ecoulement - (quantite_vendue::float / quantite_commandee)
  ) > 0.001
