---
description: Template de creation de nouvelles regles. Appliquer lors de la creation de fichiers dans .claude/rules/
globs: ".claude/rules/**"
---

- Format YAML frontmatter : description, globs (optionnel)
- Description : une ligne, complete, indique quand appliquer
- Globs : patterns de fichiers correspondants (ex: `pipelines/**/*.py`)
- Sans globs : la regle est toujours appliquee
- Contenu : bullet points uniquement, pas de titres markdown `#`
- Regles concises : 3-7 mots par bullet
- Oriente action/commande
- Backticks pour les references de code
- Pas de contenu superflu
