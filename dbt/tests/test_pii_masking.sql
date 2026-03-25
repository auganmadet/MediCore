-- Test singular : vérifie qu'aucune donnée PII n'est en clair dans staging.
-- Si cette requête retourne des lignes, des PII sont exposées.

-- Colonnes masquées par pii_mask() (format PREFIX_xxxx) :
-- - stg_fournisseurs.FOU_ADRESSE → ADDR_xxxx (adresse postale fournisseur)

-- Colonnes démasquées (raison sociale ou besoin métier, pas PII) :
-- - PHA_NOM : raison sociale pharmacie (entreprise)
-- - FOU_NOM : nom de laboratoire (entreprise)
-- - ORD_OPERATEUR : nom vendeur (nécessaire pour D5 Performance vendeurs)

select 'stg_fournisseurs.FOU_ADRESSE' as source_colonne, FOU_ADRESSE as valeur
from {{ ref('stg_fournisseurs') }}
where FOU_ADRESSE is not null
  and FOU_ADRESSE not like 'ADDR_%'
