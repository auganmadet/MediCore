---
description: Standards Python avances. Type hints complets, gestion d'erreurs, patterns idiomatiques.
globs: "**/*.py"
---

- Type hints obligatoires sur tous les parametres et retours
- `Optional[T]` pour les valeurs nullables
- `Dict[str, Any]` entre modules pour flexibilite
- `List[Dict]` pour les collections de donnees
- `bool` pour succes/echec des operations
- `ValueError` / `IOError` leves explicitement
- Logging d'erreurs en francais avec contexte
- Continuer le traitement avec warnings si possible
- F-strings pour le formatage (sauf SQL)
- Comprehensions de listes pour les transformations simples
- `enumerate()` avec `start=` pour les iterations indexees
- Guard clauses en debut de fonction
- `try/except` specifique (jamais `except Exception` nu)
- Cleanup dans `finally` pour les connexions Snowflake/Kafka
- Appels multi-lignes (`execute()`, `connect()`) : aligner les parentheses fermantes — verifier que chaque `(` a son `)` au bon niveau d'indentation
- Encapsuler les erreurs avec contexte de phase : `raise RuntimeError(f"[phase] context: {e}") from e` pour faciliter le debug
