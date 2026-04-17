---
description: Masquage PII et conformité RGPD. MD5, colonnes sensibles, vérification.
globs: "dbt/macros/**/*.sql,dbt/models/staging/**/*.sql"
---

- Macro `{{ pii_mask('column_name', 'PREFIX') }}` dans `dbt/macros/pii_masking.sql`
- Hash MD5 tronqué : produit `PREFIX_xxxx` (déterministe)
- Masquage appliqué uniquement dans staging (RAW = brut)
- Jamais de données PII en clair dans STAGING ou MARTS
- Ne jamais désactiver le masquage PII
- Vérifier le masquage après tout ajout de colonne sensible
- Tests de validation : aucun pattern nom/adresse dans staging
- Colonnes masquées : `FOU_ADRESSE` (seule PII restante, dans `stg_fournisseurs`)
- Colonnes masquées custom : `ORD_CLIENT_DEPARTMENT` (bucketed), `ORD_CLIENT_SEX`, `ORD_CLIENT_AGE_MONTHS` (dans `stg_orders`)
- Colonnes intentionnellement démasquées (raisons sociales / besoin métier) :
  - `PHA_NOM` : raison sociale pharmacie, pas une PII (entreprise)
  - `FOU_NOM` : nom laboratoire/fournisseur, pas une PII (entreprise)
  - `ORD_OPERATEUR` : nécessaire pour le dashboard D5 (Performance vendeurs)
