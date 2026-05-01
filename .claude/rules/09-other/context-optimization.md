# Optimisation du contexte Claude Code

## Objectif

Réduire la consommation de contexte pour optimiser les coûts Cortex Code (AI_SERVICES).

## Règles

### 1. Éviter de lire des fichiers volumineux inutilement

- **Ne pas lire** un fichier entier si seule une section est nécessaire
- **Utiliser `grep`** pour localiser d'abord la ligne/section pertinente
- **Utiliser `offset` et `limit`** du tool Read pour les fichiers > 500 lignes
- **Préférer** lire les fichiers de la memory-bank avant les fichiers sources

### 2. Fichiers à éviter de lire en entier

| Fichier | Lignes | Alternative |
|---------|--------|-------------|
| `docs/05_KPIs.md` | ~1300 | Lire `.claude/memory-bank/data-model.md` |
| `CHANGELOG.md` | ~270 | Lire uniquement les dernières entrées |
| Modèles dbt volumineux | Variable | Utiliser `grep` pour trouver la config |

### 3. Pattern recommandé

```bash
# Mauvais : lire tout le fichier
Read: docs/05_KPIs.md

# Bon : chercher d'abord, lire ensuite si nécessaire
Grep: "mart_kpi_univers" in docs/05_KPIs.md
Read: docs/05_KPIs.md (offset=ligne_trouvée, limit=50)
```

### 4. Memory Bank first

Toujours consulter la memory-bank en priorité :
- `data-model.md` → structure des données et KPIs
- `dbt-transformations.md` → configuration et commandes dbt
- `architecture.md` → vue d'ensemble du pipeline

## Impact estimé

- Réduction de 30-50% de la consommation AI_SERVICES
- Sessions plus longues avant épuisement du contexte
