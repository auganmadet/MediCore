---
description: Workflow Git du projet. Commits en français, branches descriptives, historique propre.
globs: ".git*,**/.gitignore,CHANGELOG.md"
---

- Messages de commit en français avec préfixe Conventional Commits
- Format : `type: message` (feat, fix, docs, chore, style, refactor, test, build)
- Commits simples, concis, atomiques
- Ne jamais mentionner Claude ou l'IA comme auteur
- Ne jamais ajouter Co-Authored-By
- Branches : kebab-case, descriptives
- Nommage : `feature/xxx`, `fix/xxx`
- Nettoyer l'historique avant merge
- Supprimer les branches mergées
- Un commit = un changement logique

Exemples :
- `feat: ajouter export CSV`
- `fix: corriger calcul marge`
- `docs: mise à jour README`
