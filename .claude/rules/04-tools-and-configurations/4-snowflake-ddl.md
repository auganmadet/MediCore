---
description: Séparation DDL_WH.sql vs DDL_TABLES.sql. Infrastructure vs schéma de données.
globs: "scripts/DDL_*.sql"
---

- `DDL_WH.sql` : infrastructure Snowflake (databases, rôles, grants, warehouse, schémas, authentication policies, fonctions RLS)
- `DDL_TABLES.sql` : tables RAW (18) + tables AUDIT (6) + GRANTS sur les tables — **source de vérité** pour le schéma AUDIT
- Ne jamais dupliquer les tables AUDIT entre les deux fichiers
- `DDL_WH.sql` crée le schéma AUDIT, `DDL_TABLES.sql` crée les tables dedans
- Les tables AUDIT dans Snowflake doivent correspondre à `DDL_TABLES.sql`
- Toute nouvelle table AUDIT → l'ajouter dans `DDL_TABLES.sql` uniquement
