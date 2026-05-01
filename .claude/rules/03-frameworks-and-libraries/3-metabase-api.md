---
description: API Metabase v0.58 pMBQL, field refs, filtres cascadés, embedding. Applicable aux scripts Metabase.
globs: "scripts/metabase_*.py,scripts/create_mbql_card.py,scripts/fix_*.py,scripts/enable_embedding.py,scripts/diagnose_cards.py,embed_app/**/*.py"
---

- Format carte pMBQL v0.58 : `stages[0]["lib/type"]` = `"mbql.stage/mbql"` (MBQL) ou `"mbql.stage/native"` (SQL natif)
- Field refs dans les expressions : `["field", field_id, None]`
- `base-type` se place au niveau **dimension target** (`["dimension", ["field", field_id, {"base-type": "type/Text"}]]`), PAS dans le field ref
- Filtres cascadés : `filteringParameters: ["pharmacie"]` sur les paramètres dépendants (fournisseur, univers, opérateur)
- Filtres date (`date/month-year`) ne supportent PAS le cascading — widget calendrier, pas de colonne source
- Convertir une carte SQL native → MBQL peut retourner 403 si les permissions sur les tables sous-jacentes sont incomplètes
- `POST /api/dataset` avec le `dataset_query` d'une carte pour tester son exécution via l'API
- Embedding signé : `enable_embedding: true` + `embedding_params: {"pharmacie": "locked", ...}` sur chaque dashboard
