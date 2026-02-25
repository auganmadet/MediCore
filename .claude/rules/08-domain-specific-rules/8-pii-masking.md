---
description: Masquage PII et conformité RGPD. MD5, colonnes sensibles, vérification.
globs: "dbt/macros/**/*.sql,dbt/models/staging/**/*.sql"
---

- Macro `{{ mask_pii('column_name') }}` dans `dbt/macros/pii_masking.sql`
- Hash MD5 pour les données personnelles
- Colonnes à masquer : noms, adresses, téléphones, emails
- Tables concernées : `stg_orders` (âge, sexe, département), `stg_pharmacie` (nom)
- Masquage appliqué uniquement dans staging (RAW = brut)
- Jamais de données PII en clair dans STAGING ou MARTS
- Ne jamais désactiver le masquage PII
- Vérifier le masquage après tout ajout de colonne sensible
- Tests de validation : aucun pattern nom/adresse dans staging
