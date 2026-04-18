# Row-Level Security — Bilan et options

## Table des matières

1. [Contexte et objectif](#contexte-et-objectif)
2. [Ce qui a été mis en place](#ce-qui-a-été-mis-en-place)
3. [Tests réalisés et résultats](#tests-réalisés-et-résultats)
4. [Problèmes rencontrés](#problèmes-rencontrés)
5. [Trois options identifiées](#trois-options-identifiées)
   - [Option A — Metabase OSS + Embedding signé](#option-a--metabase-oss--embedding-signé)
   - [Option B — Metabase Pro/Enterprise](#option-b--metabase-proenterprise)
   - [Option C — Apache Superset (open source)](#option-c--apache-superset-open-source)
6. [Comparatif](#comparatif)
7. [Recommandation](#recommandation)

---

## Contexte et objectif

MediCore est un pipeline ELT (MySQL → Kafka → Snowflake → dbt) qui alimente 16 dashboards BI pour le réseau de 268 pharmacies. L'objectif est de permettre à **chaque pharmacien de ne voir que les données de sa pharmacie**, tout en partageant les mêmes dashboards.

  ┌──────────────────────────────────────────────────────────────────────────┐
  │ Contraintes                                                              │
  ├──────────────────────────────────────────────────────────────────────────┤
  │ C1 — Pas de surcoût logiciel (si possible)                               │
  ├──────────────────────────────────────────────────────────────────────────┤
  │ C2 — Les pharmaciens n'ont pas accès à Snowflake (uniquement BI)         │
  ├──────────────────────────────────────────────────────────────────────────┤
  │ C3 — 268 pharmacies à provisionner automatiquement                       │
  ├──────────────────────────────────────────────────────────────────────────┤
  │ C4 — Dashboards en lecture seule pour les pharmaciens                    │
  ├──────────────────────────────────────────────────────────────────────────┤
  │ C5 — Les pharmaciens ne doivent pas pouvoir contourner le filtrage       │
  └──────────────────────────────────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Ce qui a été mis en place

### Côté Snowflake (fonctionnel)

  ┌──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ Composant                            │ Statut                                       │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Tables AUDIT (RLS_PHARMACY_ACCESS,   │ ✅ Créées et testées                         │
  │ RLS_PROVISION_LOG)                   │                                              │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Row Access Policies (2 policies :    │ ✅ Créées, testées, puis détachées           │
  │ PHA_ID + pharmacie_sk)               │ (inutiles avec l'Alternative A Metabase)     │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Secure functions                     │ ✅ Créées et testées                         │
  │ (RLS_CHECK_PHA_ID, RLS_CHECK_SK)     │ (dormantes, réactivables)                    │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ User Snowflake par pharmacie         │ ✅ Testé (MB_PHARMA_217)                     │
  │ (MB_PHARMA_XXX)                      │ Filtrage vérifié : ne voit que PHA_217       │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Script provision_rls.py              │ ✅ Fonctionnel (détection + provisionnement) │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Integration batch_loop.sh (04h30 FR)    │ ✅ En place                                  │
  └──────────────────────────────────────┴──────────────────────────────────────────────┘

Le filtrage **côté Snowflake fonctionne parfaitement**. Un user MB_PHARMA_217 connecté directement à Snowflake ne voit que les données de PHA_ID=217 sur les 32 tables MARTS.

### Côté Metabase OSS (partiellement fonctionnel)

  ┌──────────────────────────────────────┬──────────────────────────────────────────────┐
  │ Composant                            │ Statut                                       │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Connexion Metabase par pharmacie     │ ✅ Créée automatiquement                     │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Groupe Metabase par pharmacie        │ ✅ Créé automatiquement                      │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Collection par pharmacie             │ ✅ Créée automatiquement                     │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Copie des 16 dashboards              │ ❌ Échec (field IDs corrompus)               │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Remap field IDs après copie          │ ❌ Corrompt les dashboards originaux         │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Redirection connexion par groupe     │ ❌ Metabase OSS ne redirige pas              │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Dashboards read-only                 │ ❌ Impossible en Metabase OSS                │
  ├──────────────────────────────────────┼──────────────────────────────────────────────┤
  │ Filtres verrouillés par pharmacie    │ ❌ Impossible en Metabase OSS                │
  └──────────────────────────────────────┴──────────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Tests réalisés et résultats

### Test 1 — Multi-connexion + copie dashboards

**Principe** : 1 connexion Snowflake par pharmacie (MB_PHARMA_XXX) + Row Access Policy + copie des 16 dashboards dans chaque collection pharmacie + remap des field IDs.

**Résultat** :
- La copie des dashboards fonctionne mais les cartes gardent les field IDs de la connexion d'origine
- Le remap programmatique des field IDs (database_id, table_id, field_id dans les requêtes MBQL) **corrompt les dashboards originaux** car Metabase partage les cartes entre la copie et l'original
- Les dashboards Admin (D1-D16) ont été cassés et ont dû être restaurés manuellement (script fix_cards_db.py)
- Metabase OSS ne redirige pas les requêtes d'un dashboard vers une autre connexion selon le groupe de l'utilisateur

### Test 2 — Connexion unique + dashboards partagés

**Principe** : 1 seule connexion Metabase (MEDICORE_ANALYST) pour tout le monde + permissions par groupe + dashboards Admin partagés en lecture.

**Résultat** :
- Les dashboards s'affichent correctement pour le pharmacien ✅
- Le filtre Pharmacie fonctionne (valeurs en hash MD5) ✅
- Le pharmacien peut créer ses propres cartes dans sa collection ✅
- Le SQL natif est bloqué sur MediCore ✅
- **Mais** : le pharmacien peut **modifier les dashboards Admin** (limitation Metabase OSS : "Vue" = voir + modifier)
- **Mais** : le pharmacien peut **changer le filtre Pharmacie** et voir les données d'une autre pharmacie

### Bilan avec preuves concretes (API)

Les tests suivants ont été exécutes via l'API Metabase (script `scripts/check_permissions.py`) avec le user `test.pharmacien@test.fr` (groupe "Pharmacie du Soleil", non superuser). 
Les résultats sont indépendants de l'interface utilisateur et prouvent le comportement réel du serveur.

  ┌─────┬───────────────────────────────────────┬──────────┬──────────┬──────────────────────────────────────────────┐
  │  #  │ Test                                  │ Attendu  │ Résultat │ Preuve API                                   │
  ├─────┼───────────────────────────────────────┼──────────┼──────────┼──────────────────────────────────────────────┤
  │ P1  │ SQL natif bloque sur MediCore         │ BLOQUE   │ BLOQUE   │ POST /api/dataset (type=native)              │
  │     │                                       │          │          │ -> "Vous n'etes pas autorise"                │
  ├─────┼───────────────────────────────────────┼──────────┼──────────┼──────────────────────────────────────────────┤
  │ P2  │ Dashboard Admin non modifiable        │ BLOQUE   │ ECHOUE   │ PUT /api/dashboard/2 : renommage réussi      │
  │     │                                       │          │          │ + suppression carte réussie (9 -> 8)         │
  ├─────┼───────────────────────────────────────┼──────────┼──────────┼──────────────────────────────────────────────┤
  │ P3  │ Carte créable dans sa collection      │ AUTORISE │ AUTORISE │ POST /api/card (collection_id=52)            │
  │     │                                       │          │          │ -> card_id=413 créé                          │
  ├─────┼───────────────────────────────────────┼──────────┼──────────┼──────────────────────────────────────────────┤
  │ P4  │ Carte non créable dans Admin          │ BLOQUE   │ ECHOUE   │ POST /api/card (collection_id=21)            │
  │     │                                       │          │          │ -> card_id=414 créé (devrait être refusé)    │
  ├─────┼───────────────────────────────────────┼──────────┼──────────┼──────────────────────────────────────────────┤
  │ P5  │ Query builder fonctionne              │ AUTORISE │ AUTORISE │ POST /api/dataset (type=query)               │
  │     │                                       │          │          │ -> 5 lignes retournées                       │
  ├─────┼───────────────────────────────────────┼──────────┼──────────┼──────────────────────────────────────────────┤
  │ P6  │ Pharmacies visibles (sans RLS)        │ FILTREES │ TOUTES   │ POST /api/dataset (aggregation=count)        │
  │     │                                       │          │          │ -> 6915 lignes (toutes pharmacies)           │
  └─────┴───────────────────────────────────────┴──────────┴──────────┴──────────────────────────────────────────────┘

**3 points bloquants confirmes :**

- **P2** — Le pharmacien peut **modifier et supprimer des cartes** des dashboards Admin via `PUT /api/dashboard`. La permission "Vue" de Metabase OSS ne protège pas les dashboards en écriture.
- **P4** — Le pharmacien peut **créer des cartes dans les collections Admin** via `POST /api/card`. La permission "Vue" ne bloque pas la création de contenu.
- **P6** — Le pharmacien voit **toutes les 6915 lignes** sans aucun filtrage par pharmacie. Sans RLS côté serveur, rien n'empêche l'accès aux données des autres pharmacies via le query builder ou les filtres de dashboard.

Ces limitations sont **architecturales** (Metabase OSS ne distingue pas "voir" et "modifier" sur les collections, et ne supporte pas le Row-Level Security). Elles ne peuvent pas être contournées par la configuration.

[↑ Retour au sommaire](#table-des-matières)

---

## Problèmes rencontrés

### P1 — Copie de dashboards entre connexions : field IDs

Metabase stocke des identifiants internes (field_id, table_id) spécifiques à chaque connexion. Copier un dashboard et le pointer vers une autre connexion nécessite de remapper **tous** ces identifiants dans les requêtes MBQL, les visualization_settings, et les parameter_mappings. Ce remap est fragile, mal documenté, et a corrompu les dashboards originaux lors des tests.

### P2 — Pas de redirection de connexion par groupe

Metabase OSS lie chaque carte à une connexion fixe. Un pharmacien qui n'a accès qu'à "sa" connexion ne peut pas utiliser les dashboards créés sur la connexion Admin — il obtient une erreur de permission. Il n'y a pas de mécanisme de redirection automatique.

### P3 — Pas de dashboards read-only

En Metabase OSS, la permission "Vue" sur une collection permet de **voir ET modifier** les dashboards. Il n'existe pas de permission "voir sans modifier" dans la version gratuite. Cette granularité n'est disponible qu'en version Pro/Enterprise.

### P4 — Pas de filtres verrouillés

En Metabase OSS, les filtres de dashboard sont toujours modifiables par l'utilisateur. Il n'est pas possible de pré-remplir un filtre et de le verrouiller pour un groupe donné. Le pharmacien peut changer le filtre Pharmacie et voir les données d'une autre pharmacie (identifiée par un hash MD5 non lisible, ce qui atténue le risque sans l'éliminer).

[↑ Retour au sommaire](#table-des-matières)

---

## Trois options identifiées

### Option A — Metabase OSS + Embedding signé

**Principe** : développer une mini-application web (Flask/FastAPI) qui intègre les dashboards Metabase en iframe avec des filtres verrouillés via JWT (JSON Web Token).

```
Pharmacien → App web (authentification)
  → Génère un JWT avec pharmacie_sk verrouillé
  → Affiche le dashboard Metabase en iframe
  → Le filtre est pré-rempli ET non modifiable
  → Le dashboard est en lecture seule (pas d'UI Metabase)
```

  ┌──────────────────────────────────┬─────────────────────────────────────────────┐
  │ Avantages                        │ Inconvénients                               │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Gratuit (Metabase OSS)           │ Application web à développer et maintenir   │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Filtres verrouillés (JWT)        │ Expérience utilisateur dégradée (iframe)    │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Dashboard read-only (pas d'UI    │ Le pharmacien ne peut pas créer ses         │
  │ Metabase visible)                │ propres cartes/dashboards                   │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Infrastructure existante         │ Complexité supplémentaire (auth, JWT,       │
  │ (Metabase déjà déployé)          │ gestion des sessions, maintenance)          │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ 16 dashboards existants          │ Navigation limitée (pas d'exploration       │
  │ réutilisés sans modification     │ libre des données)                          │
  └──────────────────────────────────┴─────────────────────────────────────────────┘

**Coût** : 0 € (logiciel) + effort développement app web
**Délai estimé** : 1-2 semaines (app + intégration)

### Option B — Metabase Pro/Enterprise

**Principe** : passer à la version payante de Metabase qui offre le sandboxing natif (RLS), les filtres verrouillés, et les dashboards read-only.

```
Pharmacien → Metabase Pro (authentification native)
  → Sandboxing : filtre automatique par pharmacie via attribut utilisateur
  → Dashboard read-only (permission granulaire)
  → Filtres verrouillés par groupe
  → Query builder restreint aux données filtrées
```

  ┌──────────────────────────────────┬─────────────────────────────────────────────┐
  │ Avantages                        │ Inconvénients                               │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ RLS natif (sandboxing)           │ Coût : ~500-1500 $/mois (selon nb users)    │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Filtres verrouillés par groupe   │ Engagement annuel                           │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Dashboards read-only             │ Migration : uniquement upgrade de licence   │
  │ (granularité fine)               │ (pas de recréation)                         │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ 16 dashboards existants          │                                             │
  │ réutilisés sans modification     │                                             │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Pas de développement             │                                             │
  │ supplémentaire                   │                                             │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Support officiel Metabase        │                                             │
  └──────────────────────────────────┴─────────────────────────────────────────────┘

**Coût** : ~500-1500 $/mois (variable selon le nombre d'utilisateurs)
**Délai estimé** : 1-2 jours (upgrade licence + configuration sandboxing)

### Option C — Apache Superset (open source)

**Principe** : remplacer Metabase par Apache Superset pour la couche pharmaciens. Superset offre le Row-Level Security natif dans sa version open source gratuite. Metabase reste en place pour le Siège.

```
Pharmacien → Superset (authentification native)
  → Rôle "Pharmacie du Soleil" avec règle RLS :
    WHERE pharmacie_sk = 'a5bfc9e...'
  → Superset ajoute automatiquement le filtre à chaque requête
  → Dashboard read-only (seul le owner peut modifier)
  → Le pharmacien ne peut pas contourner le filtre
```

  ┌──────────────────────────────────┬─────────────────────────────────────────────┐
  │ Avantages                        │ Inconvénients                               │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Gratuit (open source Apache 2.0) │ 16 dashboards à recréer dans Superset       │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ RLS natif dans la version OSS    │ Deux outils BI à maintenir (Metabase        │
  │                                  │ pour le Siège + Superset pour pharmaciens)  │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Dashboards read-only par défaut  │ UI moins intuitive que Metabase             │
  │ (seul le owner peut modifier)    │ (courbe d'apprentissage)                    │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Filtrage automatique et          │ Déploiement Docker supplémentaire           │
  │ incontournable (clause WHERE     │ (Superset + Redis + PostgreSQL)             │
  │ injectée par Superset)           │                                             │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Connecteur Snowflake natif       │ Provisionnement rôles/RLS à automatiser     │
  │ (SQLAlchemy)                     │ (script provision_rls.py à adapter)         │
  ├──────────────────────────────────┼─────────────────────────────────────────────┤
  │ Scalable (268 pharmacies via     │                                             │
  │ rôles + règles RLS)              │                                             │
  └──────────────────────────────────┴─────────────────────────────────────────────┘

**Coût** : 0 € (logiciel) + effort migration dashboards
**Délai estimé** : 1-2 semaines (déploiement + recréation dashboards + provisionnement)

[↑ Retour au sommaire](#table-des-matières)

---

## Comparatif

  ┌──────────────────────────┬────────────────────┬────────────────────┬────────────────────┐
  │ Critère                  │ A — Embedding      │ B — Metabase Pro   │ C — Superset OSS   │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Coût logiciel            │ 0 €                │ 500-1500 $/mois    │ 0 €                │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Filtrage par pharmacie   │ ✅ Verrouillé      │ ✅ Verrouillé      │ ✅ Verrouillé     │
  │ (incontournable)         │ (JWT)              │ (sandboxing)       │ (RLS natif)        │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Dashboards read-only     │ ✅ (pas d'UI)      │ ✅ (granulaire)    │ ✅ (par owner)    │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ SQL natif bloqué         │ ✅                 │ ✅                 │ ✅                │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Pharmacien peut créer    │ ❌ Non             │ ✅ Oui             │ ✅ Oui (limité    │
  │ ses propres dashboards   │ (iframe)           │ (filtré par RLS)   │ par rôle)          │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ 268 pharmacies scalable  │ ✅ (JWT auto)      │ ✅ (sandboxing)    │ ✅ (rôles + RLS)  │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Réutilise les 16         │ ✅ Oui             │ ✅ Oui             │ ❌ À recréer      │
  │ dashboards existants     │                    │                    │                    │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Effort de mise en place  │ Moyen              │ Faible             │ Moyen              │
  │                          │ (app web à créer)  │ (upgrade licence)  │ (dashboards)       │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Maintenance long terme   │ Élevée             │ Faible             │ Moyenne            │
  │                          │ (app custom)       │ (support officiel) │ (2 outils BI)      │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Expérience utilisateur   │ ⚠️ Limitée ⚠️     │ ✅ Excellente ✅  │ ✅ Bonne ✅       │
  │                          │ (iframe, pas       │ (UI Metabase       │ (UI Superset,      │
  │                          │ d'exploration)     │ native)            │ moins intuitive)   │
  ├──────────────────────────┼────────────────────┼────────────────────┼────────────────────┤
  │ Risque technique         │ Moyen              │ Très faible        │ Faible             │
  │                          │ (JWT, iframe,      │ (solution éprouvée)│ (RLS natif, testé  │
  │                          │ compatibilité)     │                    │ par la communauté) │
  └──────────────────────────┴────────────────────┴────────────────────┴────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Recommandation

### Si le budget le permet : Option B — Metabase Pro

- Mise en place la plus rapide (1-2 jours)
- Aucune recréation de dashboard
- Maintenance minimale (support officiel)
- Expérience utilisateur identique à l'existant
- Coût récurrent à budgéter (~6 000-18 000 $/an)

### Si le budget est contraint : Option C — Apache Superset

- Gratuit, open source, RLS natif dans la version gratuite
- Sécurité équivalente à Metabase Pro (filtrage automatique incontournable)
- Effort initial plus important (recréation des 16 dashboards)
- Metabase reste en parallèle pour le Siège (transition progressive)
- Solution pérenne sans dépendance à une licence commerciale

### Non recommandé sauf contraintes fortes : Option A — Embedding signé

- Fonctionnel mais ajoute une couche de complexité (app web custom)
- Expérience utilisateur dégradée (iframe, pas d'exploration)
- Maintenance à long terme plus lourde
- À considérer uniquement si ni le budget (B) ni la migration (C) ne sont possibles

[↑ Retour au sommaire](#table-des-matières)
