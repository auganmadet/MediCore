---
description: Principes de code propre appliques systematiquement a tout le code Python et SQL du projet.
---

- Type hints sur toutes les signatures Python
- Constantes explicites, pas de nombres magiques
- Pas de double negation
- Noms de variables longs et lisibles
- Max 30 lignes par fonction Python
- Max 5 parametres par fonction Python
- Max 300 lignes par fichier Python
- Une responsabilite par module
- Pas de parametres booleens (flag)
- Fail fast avec retours anticipes (early return)
- Pas de code mort ou commente
- Preferer la composition a l'heritage
- Fonctions pures quand possible
- Gestion d'erreurs explicite
- SQL : un CTE par transformation logique
- SQL : pas de sous-requetes imbriquees profondes
