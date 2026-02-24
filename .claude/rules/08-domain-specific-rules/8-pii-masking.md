---
description: Masquage PII et conformite RGPD. MD5, colonnes sensibles, verification.
globs: "dbt/macros/**/*.sql,dbt/models/staging/**/*.sql"
---

- Macro `{{ mask_pii('column_name') }}` dans `dbt/macros/pii_masking.sql`
- Hash MD5 pour les donnees personnelles
- Colonnes a masquer : noms, adresses, telephones, emails
- Tables concernees : `stg_orders` (age, sexe, departement), `stg_pharmacie` (nom)
- Masquage applique uniquement dans staging (RAW = brut)
- Jamais de donnees PII en clair dans STAGING ou MARTS
- Ne jamais desactiver le masquage PII
- Verifier le masquage apres tout ajout de colonne sensible
- Tests de validation : aucun pattern nom/adresse dans staging
