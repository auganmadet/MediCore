---
description: Standards Python avancés. Type hints complets, gestion d'erreurs, patterns idiomatiques.
globs: "**/*.py"
---

- Type hints obligatoires sur tous les paramètres et retours
- `Optional[T]` pour les valeurs nullables
- `Dict[str, Any]` entre modules pour flexibilité
- `List[Dict]` pour les collections de données
- `bool` pour succès/échec des opérations
- `ValueError` / `IOError` levés explicitement
- Logging d'erreurs en français avec contexte
- Continuer le traitement avec warnings si possible
- F-strings pour le formatage (sauf SQL)
- Compréhensions de listes pour les transformations simples
- `enumerate()` avec `start=` pour les itérations indexées
- Guard clauses en début de fonction
- `try/except` spécifique (jamais `except Exception` nu)
- Cleanup dans `finally` pour les connexions Snowflake/Kafka
- Appels multi-lignes (`execute()`, `connect()`) : aligner les parenthèses fermantes — vérifier que chaque `(` a son `)` au bon niveau d'indentation
- Encapsuler les erreurs avec contexte de phase : `raise RuntimeError(f"[phase] context: {e}") from e` pour faciliter le debug
