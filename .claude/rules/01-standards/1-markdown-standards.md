---
description: Standards de documentation Markdown. Encodage, accents, tableaux, changelog.
globs: "**/*.md"
---

- Encodage UTF-8 obligatoire, caractères accentués français systématiques (é, è, ê, à, ù, î, ô, ç)
- Tableaux en format box-drawing (┌─┬─┐ │ │ ├─┼─┤ └─┴─┘) dans tous les fichiers `.md`
- En-têtes centrés, données alignées à gauche, padding 1 espace minimum par cellule
- Séparateurs horizontaux (├─┼─┤) entre chaque ligne de données
- Mettre à jour `CHANGELOG.md` pour tout changement métier ou architectural
- `CHANGELOG.md` : orienté impact métier, pas technique — catégories : Ajouts, Corrections, Modifications, Nettoyage
- `docs/05_KPIs.md` : documenter tout nouveau KPI avec formule + exemple concret
- Ne jamais modifier les fichiers `dbt/dbt_packages/**/*.md` (packages tiers)
