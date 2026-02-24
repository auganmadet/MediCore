---
description: Standards Python spécifiques au projet. PEP 8, imports, docstrings, logging.
globs: "**/*.py"
---

- PEP 8 strict pour le formatage
- Imports : stdlib -> third-party -> local (ligne vide entre)
- Docstrings Google-style en français
- Sections docstring : `Args:`, `Returns:`, `Raises:`
- Type hints : `Optional[T]`, `Dict[str, Any]`, `List[T]`
- `os.getenv()` pour toutes les variables d'environnement
- Context managers (`with`) pour les connexions DB
- Logging structuré avec `logging.getLogger(__name__)`
- Niveaux de log : INFO pour flux normal, WARNING pour fallback, ERROR pour échecs
- Pas de `print()` en production, toujours `logger`
- Classes pour les composants avec état (connexions, consumers)
- Fonctions utilitaires statiques pour la logique sans état
