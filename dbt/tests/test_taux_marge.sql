-- Test singular : le taux_marge dans mart_kpi_marge doit correspondre
-- à (ca_ht - cout_achat_net) / ca_ht pour chaque ligne.
-- Si cette requête retourne des lignes, le test échoue.

-- - mart_kpi_marge : une ligne par pharmacie × produit × jour, avec taux_marge
--   calculé comme (ca_ht - quantite_vendue * prix_achat_net) / ca_ht
-- - cout_achat_net = quantite_vendue * prix_achat_net (coût total d'achat)
-- - marge_brute = ca_ht - cout_achat_net

-- Le test recalcule taux_marge à partir de ca_ht et cout_achat_net et compare
-- avec la valeur stockée. Un écart > 0.1% signale un bug dans le calcul de marge.

select
    pharmacie_sk,
    produit_sk,
    date_jour,
    ca_ht,
    cout_achat_net,
    marge_brute,
    taux_marge,
    case
        when ca_ht != 0
        then (ca_ht - cout_achat_net) / ca_ht
        else null
    end as taux_marge_attendu,
    abs(
        taux_marge - case
            when ca_ht != 0
            then (ca_ht - cout_achat_net) / ca_ht
            else null
        end
    ) as ecart
from {{ ref('mart_kpi_marge') }}
where ca_ht != 0
  and taux_marge is not null
  and abs(
      taux_marge - (ca_ht - cout_achat_net) / ca_ht
  ) > 0.001
