---
description: Limitations Metabase OSS prouvées par tests API. RLS, permissions, filtres verrouillés.
globs: "scripts/metabase_*.py,scripts/provision_rls.py,embed_app/**/*.py,docs/1[2-5]_*.md"
---

- Metabase OSS n'a PAS de Row-Level Security natif — impossible de rediriger les requêtes selon le groupe
- Pas de dashboard read-only : permission "Vue" = voir + modifier via `PUT /api/dashboard`
- Pas de filtre verrouillé : les filtres de dashboard sont toujours modifiables par l'utilisateur
- Contournement retenu : embedding signé (JWT) avec filtre `pharmacie` locked dans le token — le pharmacien ne voit que ses données
- Alternative A en production : 1 connexion `MEDICORE_ANALYST`, embedding signé, filtre pharmacie_sk verrouillé par JWT
- Les cartes MBQL sont préférées aux SQL natives pour l'embedding (meilleure gestion des filtres, cascading, listes de valeurs)
