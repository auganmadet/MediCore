---
description: Template de création de nouvelles règles. Appliquer lors de la création de fichiers dans .claude/rules/
globs: ".claude/rules/**"
---

- Format YAML frontmatter : description, globs (optionnel)
- Description : une ligne, complète, indique quand appliquer
- Globs : patterns de fichiers correspondants (ex: `pipelines/**/*.py`)
- Sans globs : la règle est toujours appliquée
- Contenu : bullet points uniquement, pas de titres markdown `#`
- Règles concises : 3-7 mots par bullet
- Orienté action/commande
- Backticks pour les références de code
- Pas de contenu superflu
