---
description: Workflow Git du projet. Commits en français, branches descriptives, historique propre.
globs: ".git*,**/.gitignore,CHANGELOG.md"
---

- Conventional Commits obligatoire : `type: message en français`
- Types : `feat:`, `fix:`, `chore:`, `docs:`, `style:`, `refactor:`, `test:`, `build:`, `ci:`
- Messages de commit en français après le préfixe
- Commits simples, concis, atomiques
- Ne jamais mentionner Claude, Cortex ou l'IA comme auteur
- Ne jamais ajouter `Co-Authored-By` ou `Generated With`
- Branches : kebab-case, descriptives
- Nommage : `feature/xxx`, `fix/xxx`
- Nettoyer l'historique avant merge
- Supprimer les branches mergées
- Un commit = un changement logique
