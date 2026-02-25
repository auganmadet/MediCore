---
description: Principes de code propre appliqués systématiquement à tout le code Python et SQL du projet.
---

- Type hints sur toutes les signatures Python
- Constantes explicites, pas de nombres magiques
- Pas de double négation
- Noms de variables longs et lisibles
- Max 30 lignes par fonction Python
- Max 5 paramètres par fonction Python
- Max 300 lignes par fichier Python
- Une responsabilité par module
- Pas de paramètres booléens (flag)
- Fail fast avec retours anticipés (early return)
- Pas de code mort ou commenté
- Préférer la composition à l'héritage
- Fonctions pures quand possible
- Gestion d'erreurs explicite
- SQL : un CTE par transformation logique
- SQL : pas de sous-requêtes imbriquées profondes
