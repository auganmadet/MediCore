# Checklist de dépannage Metabase

## Table des matières

1. [En temps normal : un seul script](#en-temps-normal--un-seul-script)
2. [Architecture de l'orchestrateur](#architecture-de-lorchestateur)
3. [Checklist par symptôme](#checklist-par-symptôme)
4. [Annexe A — Dictionnaire des scripts](#annexe-a--dictionnaire-des-scripts)
5. [Annexe B — Comment récupérer les paramètres des scripts](#annexe-b--comment-récupérer-les-paramètres-des-scripts)
6. [Annexe C — Référence des problèmes (P1-P10)](#annexe-c--référence-des-problèmes-p1-p10)

---

## En temps normal : un seul script

```bash
python scripts/metabase_maintenance.py
```

C'est tout. Ce script détecte et corrige **automatiquement** les 10 problèmes identifiés (P1-P10). Il s'auto-authentifie via `.env` — pas besoin de passer un token. Il est appelé par `pipeline_maintenance.py --fix-safe` qui tourne chaque nuit à 04h30 FR dans `batch_loop.sh`.

Autres modes d'exécution :

```bash
# Simulation : détecte sans corriger
python scripts/metabase_maintenance.py --dry-run

# Diagnostiquer une carte spécifique
python scripts/metabase_maintenance.py --diagnose --card 369

# Diagnostiquer un dashboard complet
python scripts/metabase_maintenance.py --diagnose --dashboard 5

# Provisionner une seule pharmacie
python scripts/metabase_maintenance.py --pha-id 217
```

**Quand utiliser les scripts individuels ?** Uniquement en cas de dépannage ponctuel :
- `metabase_maintenance.py` a timeout sur une étape → relancer uniquement cette étape
- Investigation d'un problème spécifique sur une carte ou un dashboard
- Voir [Annexe A — Dictionnaire des scripts](#annexe-a--dictionnaire-des-scripts)

[↑ Retour au sommaire](#table-des-matières)

---

## Architecture de l'orchestrateur

`metabase_maintenance.py` est un orchestrateur qui appelle les scripts existants — il ne les remplace pas :

```
scripts/metabase_maintenance.py (orchestrateur)
  │
  ├── S'auto-authentifie (token Metabase + Snowflake via .env)
  │
  ├── Détecte P1  → appelle fix_cards_db.py
  ├── Détecte P2  → appelle fix_cards_db_name.py
  ├── Détecte P3/P8/P9 → appelle create_mbql_card.py
  ├── Détecte P4  → appelle fix_filter_widgets.py
  ├── Détecte P5  → appelle fix_dashboard_date_params.py
  ├── Détecte P6  → appelle enable_embedding.py
  ├── Détecte P7  → appelle diagnose_cards.py
  ├── Détecte P10 → appelle provision_rls.py
  │
  └── Rapport final (détectés / corrigés / manuels)
```

Chaque script reste utilisable individuellement pour le dépannage ponctuel. `metabase_maintenance.py` les orchestre en séquence et passe le token automatiquement.

[↑ Retour au sommaire](#table-des-matières)

---

## Checklist par symptôme

### Toutes les cartes d'un dashboard affichent "Un problème est survenu"

```
Cause probable : P1 (mauvais database_id)

1. Lancer : python scripts/metabase_maintenance.py
   → Corrige automatiquement P1

2. Si le problème persiste :
   python scripts/metabase_maintenance.py --diagnose --dashboard <id>
   → Identifier la cause exacte (P2, P7...)
```

### Une seule carte affiche "Un problème est survenu"

```
Cause probable : P2 (ancien nom database) ou P3 (syntaxe SQL) ou P7 (erreur générique)

1. Lancer : python scripts/metabase_maintenance.py
   → Corrige automatiquement P1 et P2

2. Si le problème persiste :
   python scripts/metabase_maintenance.py --diagnose --card <card_id>
   → Le script affiche le dataset_query et exécute la carte pour identifier l'erreur

3. Si l'erreur est "Database 'MEDICORE' does not exist" :
   → P2 : le script de maintenance l'a déjà corrigé, recharger la page

4. Si l'erreur est une erreur SQL spécifique :
   → Corriger le SQL manuellement dans Metabase (mode édition de la carte)
   → Ou recréer en MBQL : python scripts/create_mbql_card.py --card <card_id>
```

### Carte OK sur localhost:3000 mais erreur sur localhost:5000

```
Cause probable : P8 (carte SQL native avec template-tag date incompatible embedding)

1. Lancer : python scripts/metabase_maintenance.py
   → Détecte P8 et recrée la carte en MBQL automatiquement

2. Si la carte n'est pas dans KNOWN_CARDS de create_mbql_card.py :
   → Ajouter la définition MBQL dans le dictionnaire KNOWN_CARDS
   → Puis relancer : python scripts/create_mbql_card.py --card <card_id>
```

### Filtre sans liste de valeurs (champ de saisie vide)

```
Cause probable : P4 (widget pas en liste) ou P9 (mappé uniquement à des SQL natives)

1. Lancer : python scripts/metabase_maintenance.py
   → Corrige automatiquement P4

2. Si le filtre est en "liste déroulante" mais toujours pas de valeurs :
   → P9 : le filtre est mappé uniquement à des cartes SQL natives
   → Le script de maintenance recrée les cartes en MBQL (P8/P9)

3. Si le problème persiste :
   python scripts/metabase_maintenance.py --diagnose --dashboard <id>
   → Vérifier les parameter_mappings : au moins une carte MBQL doit avoir
     un mapping ["dimension", ["field", <id>, ...]] pour ce filtre
```

### Filtre date affiche un calendrier avec intervalle (début/fin)

```
Cause probable : P5 (date/range au lieu de date/month-year)

Lancer : python scripts/metabase_maintenance.py
→ Corrige automatiquement P5
```

### Dashboard non visible dans la mini-app Flask (iframe vide ou blanc)

```
Cause probable : P6 (embedding non activé)

1. Lancer : python scripts/metabase_maintenance.py
   → Corrige automatiquement P6

2. Vérifier aussi que METABASE_EMBEDDING_SECRET_KEY est dans .env
```

### Nouvelle pharmacie non visible dans la mini-app Flask

```
Cause probable : P10 (pharmacie non provisionnée dans Metabase)

1. Vérifier que la pharmacie est dans dim_pharmacie :
   SELECT * FROM MEDICORE_PROD.MARTS.DIM_PHARMACIE WHERE PHA_ID = <id>

2. Si présente : python scripts/metabase_maintenance.py
   → Détecte et provisionne automatiquement (P10)

3. Si absente : le CDC ou dbt n'a pas encore traité l'INSERT MySQL.
   Attendre le prochain cycle batch_loop (mode jour : ~60 min).
```

### Metabase sature / timeout lors de l'exécution d'un script

```
Cause : Metabase v0.58 a une limite de requêtes simultanées.

1. Attendre 2 minutes
2. Relancer le script individuel avec --start <N> pour reprendre
   (disponible sur fix_cards_db.py, fix_cards_db_name.py, enable_embedding.py)
3. Si le timeout persiste : redémarrer Metabase
   docker compose restart metabase
```

[↑ Retour au sommaire](#table-des-matières)

---

## Annexe A — Dictionnaire des scripts

### Scripts de correction (appelés par metabase_maintenance.py)

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────┬─────────────┬──────────────────────────────────────────────────┐
  │ Script                              │ Rôle                                             │ Problème(s) │ Usage                                            │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼─────────────┼──────────────────────────────────────────────────┤
  │ fix_cards_db.py                     │ Corrige database_id sur toutes les cartes        │ P1          │ python scripts/fix_cards_db.py <token>           │
  │                                     │ des 16 dashboards                                │             │ [--start N]                                      │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼─────────────┼──────────────────────────────────────────────────┤
  │ fix_cards_db_name.py                │ Remplace MEDICORE. par MEDICORE_PROD.            │ P2          │ python scripts/fix_cards_db_name.py <token>      │
  │                                     │ dans les SQL natives                             │             │ [--dry-run] [--start N]                          │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼─────────────┼──────────────────────────────────────────────────┤
  │ create_mbql_card.py                 │ Recrée une carte SQL native en MBQL et           │ P3, P8, P9  │ python scripts/create_mbql_card.py               │
  │                                     │ remplace dans le dashboard                       │             │ --card <id> [--card <id>] [--dry-run]            │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼─────────────┼──────────────────────────────────────────────────┤
  │ fix_filter_widgets.py               │ Force les filtres texte en liste déroulante      │ P4          │ python scripts/fix_filter_widgets.py <token>     │
  │                                     │                                                  │             │ [--dry-run]                                      │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼─────────────┼──────────────────────────────────────────────────┤
  │ fix_dashboard_date_params.py        │ Change date/range en date/month-year             │ P5          │ python scripts/fix_dashboard_date_params.py      │
  │                                     │                                                  │             │ <token>                                          │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼─────────────┼──────────────────────────────────────────────────┤
  │ enable_embedding.py                 │ Active l'embedding + configure les               │ P6          │ python scripts/enable_embedding.py <token>       │
  │                                     │ paramètres locked/enabled                        │             │ [--start N]                                      │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼─────────────┼──────────────────────────────────────────────────┤
  │ provision_rls.py                    │ Provisionnement pharmacies (groupe +             │ P10         │ python scripts/provision_rls.py --run-id <id>    │
  │                                     │ collection + permissions Metabase)               │             │ [--pha-id N] [--dry-run]                         │
  └─────────────────────────────────────┴──────────────────────────────────────────────────┴─────────────┴──────────────────────────────────────────────────┘

### Scripts de diagnostic

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────┬──────────────────────────────────────────────────┐
  │ Script                              │ Rôle                                             │ Usage                                            │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ check_all_dashboards.py             │ Audit complet : exécute chaque carte, vérifie    │ python scripts/check_all_dashboards.py <token>   │
  │                                     │ filtres et embedding                             │                                                  │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ diagnose_cards.py                   │ Diagnostic détaillé : field IDs invalides,       │ python scripts/diagnose_cards.py <token>         │
  │                                     │ exécution, erreurs SQL                           │ --dashboard <id>                                 │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ show_card_query.py                  │ Affiche le dataset_query complet d'une carte     │ python scripts/show_card_query.py <token>        │
  │                                     │ (investigation)                                  │ <card_id>                                        │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ show_dashboard_params.py            │ Affiche les paramètres et mappings d'un          │ python scripts/show_dashboard_params.py <token>  │
  │                                     │ dashboard                                        │ <dash_id>                                        │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ check_fields.py                     │ Vérifie les métadonnées d'un champ               │ python scripts/check_fields.py <token>           │
  │                                     │ (has_field_values, semantic_type)                │ <field_id> [field_id ...]                        │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ check_field_values.py               │ Affiche les valeurs cachées d'un champ           │ python scripts/check_field_values.py <token>     │
  │                                     │ (contenu de la liste déroulante)                 │ <field_id> [field_id ...]                        │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ check_permissions.py                │ Teste les permissions effectives d'un            │ python scripts/check_permissions.py              │
  │                                     │ utilisateur via l'API                            │ <email> <password>                               │
  └─────────────────────────────────────┴──────────────────────────────────────────────────┴──────────────────────────────────────────────────┘

### Scripts utilitaires

  ┌─────────────────────────────────────┬──────────────────────────────────────────────────┬──────────────────────────────────────────────────┐
  │ Script                              │ Rôle                                             │ Usage                                            │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ get_token.py                        │ Récupère un token de session Metabase admin      │ python scripts/get_token.py                      │
  │                                     │ (pour les scripts qui demandent <token>)         │                                                  │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ list_dashboards.py                  │ Liste les dashboards avec leur collection        │ python scripts/list_dashboards.py <token>        │
  │                                     │ (chemin complet)                                 │                                                  │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ list_users.py                       │ Liste les utilisateurs Metabase avec leur statut │ python scripts/list_users.py <token>             │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ reset_password.py                   │ Réinitialise le mot de passe d'un utilisateur    │ python scripts/reset_password.py <token>         │
  │                                     │ Metabase                                         │ <user_id> <password>                             │
  ├─────────────────────────────────────┼──────────────────────────────────────────────────┼──────────────────────────────────────────────────┤
  │ get_embedding_key.py                │ Active l'embedding signé et récupère la clé      │ python scripts/get_embedding_key.py <token>      │
  │                                     │ secrète Metabase                                 │                                                  │
  └─────────────────────────────────────┴──────────────────────────────────────────────────┴──────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Annexe B — Comment récupérer les paramètres des scripts

Certains scripts nécessitent un `<token>`, un `<card_id>` ou un `<dashboard_id>`. Voici comment les obtenir :

### Token Metabase (`<token>`)

```bash
# Auto-authentification via .env (recommandé)
python scripts/get_token.py
# Affiche : fe27de62-9269-4843-8619-c68746895d25

# Le token est valide ~14 jours. Le réutiliser jusqu'à erreur 401.
```

> **Note** : `metabase_maintenance.py` s'auto-authentifie — pas besoin de token. Les scripts individuels (`fix_*.py`, `enable_embedding.py`, etc.) nécessitent le token en premier argument.

### ID d'un dashboard (`<dashboard_id>`)

L'ID est visible dans l'URL Metabase :

```
http://localhost:3000/dashboard/5  →  dashboard_id = 5

Mapping D1-D16 :
  D1=2, D2=3, D3=4, D4=5, D5=6, D6=7, D7=8, D8=9,
  D9=10, D10=11, D11=12, D12=13, D13=14, D14=15, D15=16, D16=17
```

Ou via le script :

```bash
python scripts/list_dashboards.py <token>
```

### ID d'une carte (`<card_id>`)

1. **Depuis Metabase** : ouvrir le dashboard → cliquer sur une carte → l'ID est dans l'URL :
   ```
   http://localhost:3000/question/369  →  card_id = 369
   ```

2. **Depuis un script de diagnostic** :
   ```bash
   python scripts/metabase_maintenance.py --diagnose --dashboard 5
   # Affiche toutes les cartes du dashboard avec leur ID :
   #   card 62: OK - Marge brute par jour
   #   card 369: ERREUR - Distribution taux de marge
   ```

3. **Depuis l'audit complet** :
   ```bash
   python scripts/check_all_dashboards.py <token>
   # Liste toutes les cartes de tous les dashboards avec leur statut
   ```

### ID d'un champ (`<field_id>`)

Utilisé par `check_fields.py` et `check_field_values.py` :

```bash
# Depuis le diagnostic d'un dashboard (affiche les field IDs dans les mappings) :
python scripts/show_dashboard_params.py <token> 5
# Affiche : param=pharmacie -> target=["dimension", ["field", 356, ...]]
#                                                           ^^^ field_id = 356
```

### ID d'un utilisateur (`<user_id>`)

```bash
python scripts/list_users.py <token>
# Affiche :   1  actif     augustin.madet@mediprix.fr        Augan MADET
#             5  actif     test.pharmacien@test.fr            Test Pharmacien
#                                                             ^^^ user_id = 5
```

[↑ Retour au sommaire](#table-des-matières)

---

## Annexe C — Référence des problèmes (P1-P10)

### P1 — Cartes avec mauvais database_id

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ Triangles jaunes "Un problème est survenu" sur toutes les cartes d'un dashboard                 │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Les cartes Metabase référencent une connexion supprimée (database_id=6) au lieu de la           │
  │             │ connexion MediCore (database_id=2). Causé par la tentative de remap field IDs lors des          │
  │             │ tests RLS multi-connexion.                                                                      │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ `GET /api/card/{id}` → vérifier `database_id != 2` ET `dataset_query.database != 2`             │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ `PUT /api/card/{id}` avec `database_id=2` ET `dataset_query.database=2`. Les deux champs        │
  │             │ doivent être corrigés simultanément. Pause de 2s entre chaque carte.                            │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/fix_cards_db.py <token> [--start N]`                                            │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P2 — SQL native référence MEDICORE au lieu de MEDICORE_PROD

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ "Database 'MEDICORE' does not exist or not authorized"                                          │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Renommage de la database Snowflake de MEDIcore vers MEDICORE_PROD (2026-03-24). Les cartes      │
  │             │ SQL natives contiennent le nom en dur. Les cartes MBQL ne sont pas affectées (elles référencent │
  │             │ la connexion par son ID interne).                                                               │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ `GET /api/card/{id}` → chercher `"MEDICORE."` dans `stages[0].native` en s'assurant qu'elle     │
  │             │ n'est PAS suivie de `"PROD"`.                                                                   │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ Remplacement de texte `"MEDICORE."` → `"MEDICORE_PROD."` via `PUT /api/card/{id}`.              │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/fix_cards_db_name.py <token> [--dry-run] [--start N]`                           │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P3 — SQL native avec syntaxe cassée

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ Carte exécutable sans filtre mais erreur quand un filtre est appliqué.                          │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Erreurs humaines dans le SQL natif : double accolade `{{pharmacie}}}}`, filtre `WHERE` placé    │
  │             │ après `GROUP BY ... ORDER BY`, guillemets manquants autour de `{{pharmacie}}` pour les VARCHAR. │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ `POST /api/dataset` avec le `dataset_query` → vérifier si la réponse contient `error`.          │
  │             │ Tester avec ET sans paramètres de filtre pour détecter les erreurs conditionnelles.             │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ Recréer la carte en MBQL via l'API `POST /api/card`. Le MBQL est généré automatiquement         │
  │             │ à partir de la table source, des agrégations et des expressions `case()`.                       │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/create_mbql_card.py --card <card_id>`                                           │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P4 — Filtres texte pas en mode liste déroulante

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ Le filtre demande de taper du texte au lieu de proposer une liste de valeurs cliquable.         │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Metabase crée les filtres en mode "champ de saisie" par défaut. Slugs concernés : pharmacie,    │
  │             │ fournisseur, univers, operateur, statut_dormant.                                                │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ `GET /api/dashboard/{id}` → pour chaque paramètre `string/*`, vérifier                          │
  │             │ `values_query_type != "list"`.                                                                  │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ `PUT /api/dashboard/{id}` avec `parameters` mis à jour : changer `values_query_type` en         │
  │             │ `"list"` pour chaque filtre texte.                                                              │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/fix_filter_widgets.py <token> [--dry-run]`                                      │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P5 — Filtre date en date/range au lieu de date/month-year

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ Le filtre affiche un calendrier avec "début" et "fin" au lieu d'un sélecteur mois/année.        │
  │             │ Incompatible avec les cartes SQL natives en mode embedding (signed embedding).                  │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Le type `date/range` envoie un intervalle que les template-tags SQL natifs ne gèrent pas        │
  │             │ en embedding. Le type `date/month-year` fonctionne car il envoie une seule valeur.              │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ `GET /api/dashboard/{id}` → vérifier `parameters[].type == "date/range"`.                       │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ `PUT /api/dashboard/{id}` → changer `type` en `"date/month-year"`, renommer `slug` et `id`      │
  │             │ de `"date"` en `"mois"`, renommer `name` en `"Mois"`. Mettre à jour les `parameter_mappings`    │
  │             │ de chaque dashcard pour remplacer `parameter_id: "date"` par `parameter_id: "mois"`.            │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/fix_dashboard_date_params.py <token>`                                           │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P6 — Embedding non activé sur un dashboard

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ L'iframe dans la mini-app Flask affiche une erreur ou un écran blanc. Nécessaire pour que       │
  │             │ les pharmaciens voient les dashboards via l'application Mediprix.                               │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Le dashboard n'est pas publié en mode "signed embedding".                                       │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ `GET /api/dashboard/{id}` → vérifier `enable_embedding == false`. Vérifier aussi que            │
  │             │ `embedding_params` contient `pharmacie: "locked"` et les autres filtres en `"enabled"`.         │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ `PUT /api/dashboard/{id}` avec `enable_embedding: true` et `embedding_params` configuré :       │
  │             │ le slug `pharmacie` est mis en `"locked"`, tous les autres en `"enabled"`.                      │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/enable_embedding.py <token> [--start N]`                                        │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P7 — Carte non exécutable (erreur générique)

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ Triangle jaune "Un problème est survenu". Métadonnées (database_id, field IDs) semblent         │
  │             │ correctes. Causes possibles : table Snowflake supprimée/renommée, colonne supprimée/renommée,   │
  │             │ erreur SQL dans une requête native, timeout de requête, problème de permissions Snowflake.      │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Multiple — le message d'erreur permet d'identifier la cause exacte ("Table does not exist",     │
  │             │ "Invalid column", "SQL compilation error", etc.).                                               │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ `GET /api/card/{id}` pour récupérer le `dataset_query`, puis `POST /api/dataset` avec ce        │
  │             │ query → vérifier si la réponse contient `error`.                                                │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ Selon la cause : si table/colonne renommée → mettre à jour le SQL ou les field IDs.             │
  │             │ Si erreur SQL native → recréer en MBQL. Si timeout → simplifier la requête.                     │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ Diagnostic : `python scripts/diagnose_cards.py <token> --dashboard <id>`                        │
  │             │ Investigation : `python scripts/show_card_query.py <token> <card_id>`                           │
  │             │ Recréation : `python scripts/create_mbql_card.py --card <card_id>`                              │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P8 — Carte SQL native avec template-tag date incompatible embedding

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ Carte OK sur localhost:3000 mais triangle jaune sur localhost:5000 (mini-app Flask).            │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Metabase v0.58 gère différemment les paramètres `date` en mode embedding pour les cartes        │
  │             │ SQL natives — le format de la valeur envoyée par le JWT n'est pas compatible avec le            │
  │             │ template-tag. Les cartes MBQL ne sont pas affectées.                                            │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ Pour chaque carte SQL native d'un dashboard embedded, vérifier `stages[0].template-tags`        │
  │             │ → si un tag a `type: "date"`, c'est un risque.                                                  │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ Recréer la carte en MBQL via l'API : 1) lire le SQL natif, 2) identifier la table et les        │
  │             │ field IDs via `/api/database/{id}/metadata`, 3) construire l'équivalent MBQL avec expressions   │
  │             │ `case()`, 4) `POST /api/card`, 5) `PUT /api/dashboard/{id}` pour remplacer avec les bons        │
  │             │ `parameter_mappings` (`["dimension", ["field", ...]]` au lieu de `["variable", ...]`).          │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/create_mbql_card.py --card <card_id>`                                           │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P9 — Filtre sans liste de valeurs (mappé uniquement à des SQL natives)

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ Le filtre affiche un champ de saisie vide même si `values_query_type = "list"`.                 │
  │             │ Ex: D11 (Produits dormants) fonctionne car ses cartes MBQL sont mappées au filtre Univers ;     │
  │             │ D4 (Marge détaillée) ne fonctionnait pas car seule la carte 407 (SQL native) était mappée.      │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ Le filtre est mappé uniquement via `["variable", ["template-tag", "univers"]]` (cartes SQL      │
  │             │ natives). Metabase ne peut pas proposer de liste car il ne sait pas quelle table/colonne        │
  │             │ contient les valeurs. Seules les cartes MBQL avec `["dimension", ["field", field_id, ...]]`     │
  │             │ permettent à Metabase de résoudre la colonne et charger les valeurs.                            │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ Pour chaque paramètre `string/*` d'un dashboard, examiner les `parameter_mappings` → si         │
  │             │ TOUTES utilisent `["variable", ["template-tag", ...]]` et AUCUNE n'utilise                      │
  │             │ `["dimension", ["field", ...]]`, le filtre n'aura pas de liste.                                 │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ Recréer la carte SQL native en MBQL (même processus que P8) puis remplacer dans le dashboard.   │
  │             │ La nouvelle carte MBQL sera mappée via `["dimension", ["field", field_id, ...]]`.               │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/create_mbql_card.py --card <card_id>`                                           │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

### P10 — Nouvelles pharmacies à provisionner dans Metabase

  ┌─────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ Symptôme    │ La pharmacie n'apparaît pas dans la mini-app Flask. Détection automatique chaque nuit à         │
  │             │ 04h30 FR via `batch_loop.sh` (pipeline_maintenance.py).                                                                      │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Cause       │ La pharmacie existe dans `dim_pharmacie` (Snowflake) mais n'a pas encore de groupe ni de        │
  │             │ collection dans Metabase.                                                                       │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Détection   │ `SELECT dim.PHA_ID, dim.PHA_NOM FROM MARTS.DIM_PHARMACIE dim LEFT JOIN`                         │
  │             │ `AUDIT.RLS_PHARMACY_ACCESS r ON dim.PHA_ID = r.PHA_ID WHERE r.PHA_ID IS NULL`                   │
  │             │ `AND dim.PHA_ID != -1`                                                                          │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Correction  │ Provisionnement complet via les APIs Metabase : 1) créer ou trouver la collection "Pharmacies"  │
  │             │ sous MediCore BI, 2) créer le groupe, 3) créer la collection de la pharmacie, 4) configurer     │
  │             │ data: query-builder + native=none, 5) configurer collection: Vue sur MediCore BI + Curate       │
  │             │ sur sa collection, 6) INSERT dans `AUDIT.RLS_PHARMACY_ACCESS`.                                  │
  ├─────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Script      │ `python scripts/provision_rls.py --run-id <id> [--pha-id N] [--dry-run]`                        │
  └─────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)
