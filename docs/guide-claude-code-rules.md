# Guide pratique — CLAUDE.md et Rules dans Claude Code

**Préconisations, mécanismes et retour d'expérience**

> Date : 2026-02-24
> Projet de référence : MediCore (pipeline ELT pharmacie)
> Auteur : Équipe MediCore

---

## Table des matières

1. [Pourquoi ce document ?](#1-pourquoi-ce-document-)
2. [Le problème : travailler sans instructions persistantes](#2-le-problème--travailler-sans-instructions-persistantes)
3. [La solution : CLAUDE.md et .claude/rules/](#3-la-solution--claudemd-et-clauderules)
4. [Mécanisme de chargement — ce que Claude Code lit vraiment](#4-mécanisme-de-chargement--ce-que-claude-code-lit-vraiment)
5. [Pourquoi .ai-development/ n'est pas performant](#5-pourquoi-ai-development-nest-pas-performant)
6. [Architecture recommandée du dossier .claude/](#6-architecture-recommandée-du-dossier-claude)
7. [CLAUDE.md — le fichier constitutionnel](#7-claudemd--le-fichier-constitutionnel)
8. [Les Rules — des instructions ciblées et modulaires](#8-les-rules--des-instructions-ciblées-et-modulaires)
9. [Frontmatter et globs : le chargement conditionnel](#9-frontmatter-et-globs--le-chargement-conditionnel)
10. [Hiérarchie de priorité des instructions](#10-hiérarchie-de-priorité-des-instructions)
11. [Bonnes pratiques issues du terrain](#11-bonnes-pratiques-issues-du-terrain)
12. [Résultats concrets observés sur MediCore](#12-résultats-concrets-observés-sur-medicore)
13. [Objections courantes et réponses](#13-objections-courantes-et-réponses)
14. [Limites connues](#14-limites-connues)
15. [Checklist de mise en place](#15-checklist-de-mise-en-place)
16. [Sources officielles](#16-sources-officielles)

---

## 1. Pourquoi ce document ?

Claude Code est un assistant CLI puissant, mais sans instructions persistantes, chaque nouvelle session repart de zéro. L'assistant redécouvre l'architecture, réinvente les conventions, et reproduit des erreurs déjà corrigées.

Ce document explique comment structurer des fichiers d'instructions (CLAUDE.md et Rules) pour que Claude Code travaille avec une connaissance durable du projet. Il s'adresse à ceux qui doutent de l'utilité de ces fichiers ou qui les placent au mauvais endroit.

---

## 2. Le problème : travailler sans instructions persistantes

Sans CLAUDE.md ni Rules, voici ce qui se passe à chaque session :

- Claude ignore les conventions de nommage du projet
- Claude ne connaît pas l'architecture (couches RAW/STG/MARTS, CDC, etc.)
- Claude répète des erreurs déjà identifiées et corrigées (ex. : fuite de curseurs Snowflake, fichiers COPY INTO ignorés après TRUNCATE, processus zombies Docker)
- Claude propose des solutions inadaptées au contexte technique
- Le développeur doit ré-expliquer le même contexte à chaque session
- Les revues de code révèlent des incohérences entre sessions

**Conséquence** : perte de temps, frustration et qualité inégale.

---

## 3. La solution : CLAUDE.md et .claude/rules/

Claude Code propose deux mécanismes complémentaires d'instructions persistantes :

### CLAUDE.md

Fichier Markdown chargé automatiquement dans le prompt système au démarrage de chaque session. Il contient les directives globales du projet : architecture, conventions, commandes, sécurité.

### .claude/rules/*.md

Dossier de fichiers Markdown modulaires, chacun dédié à un domaine précis (tests dbt, connecteur Snowflake, workflow Git...). Ils sont chargés automatiquement — soit inconditionnellement, soit uniquement quand Claude travaille sur des fichiers correspondant à un glob défini dans leur frontmatter.

Ensemble, ils forment la **« mémoire projet »** de Claude Code.

---

## 4. Mécanisme de chargement — ce que Claude Code lit vraiment

Au lancement d'une session, Claude Code charge automatiquement :

1. **Les fichiers CLAUDE.md** dans la hiérarchie de répertoires (du répertoire courant jusqu'à la racine)

2. **Tous les fichiers `.md` dans `.claude/rules/`** (récursivement)
   - Sans frontmatter `paths` / `globs` : chargés systématiquement
   - Avec frontmatter `paths` / `globs` : chargés uniquement si Claude travaille sur des fichiers correspondant aux patterns

3. **Le fichier `.claude/CLAUDE.md`** (équivalent au CLAUDE.md racine mais dans le dossier `.claude/`)

4. **Les fichiers `CLAUDE.local.md`** (instructions personnelles, non versionnées, ajoutées automatiquement au `.gitignore`)

### Ce que Claude Code ne charge PAS automatiquement

> **IMPORTANT** : les emplacements suivants ne sont **PAS** injectés automatiquement dans le prompt système.

- `.ai-development/` — format Cursor IDE, lisible mais non injecté (voir [section 5](#5-pourquoi-ai-development-nest-pas-performant))
- `.cursorrules` — format Cursor IDE
- `.cursor/rules/` — format Cursor IDE
- `.github/copilot/` — format GitHub Copilot
- Tout autre dossier non standard

Ces emplacements appartiennent à d'autres outils. Claude Code **peut** techniquement les lire si on lui demande, mais il ne les charge pas au démarrage — contrairement à `.claude/rules/` qui est injecté automatiquement.

---

## 5. Pourquoi .ai-development/ n'est pas performant

Certains projets utilisent un dossier `.ai-development/` pour stocker des fichiers `.mdc` (Markdown Components, format Cursor IDE). Claude Code **peut** techniquement les lire — ce ne sont pas des fichiers invisibles. Mais il y a une différence majeure de performance.

### Ce qui se passe avec `.claude/rules/*.md`

Les fichiers dans `.claude/rules/` sont **injectés automatiquement** dans le prompt système au démarrage de la session. Claude les connaît **avant même la première interaction** — zéro coût supplémentaire, zéro délai.

### Ce qui se passe avec `.ai-development/*.mdc`

Les fichiers dans `.ai-development/` ne sont **pas injectés automatiquement**. Pour que Claude les prenne en compte, il doit :

1. **Découvrir** que le dossier existe (exploration du projet)
2. **Lire** chaque fichier `.mdc` un par un (appels d'outils Read)
3. **Parser** le frontmatter Cursor IDE (format différent de Claude Code)
4. **Interpréter** le contenu comme des instructions (best effort, aucune garantie)

Chacune de ces étapes **consomme du contexte** (tokens). Sur un projet avec 20 fichiers de règles, cela représente des milliers de tokens dépensés à chaque session juste pour retrouver des instructions qui auraient été gratuites dans `.claude/rules/`.

### Comparaison concrète

  ┌──────────────────────────┬──────────────────────────┬───────────────────────────┐
  │        Critère           │   `.claude/rules/*.md`   │ `.ai-development/*.mdc`   │
  ├──────────────────────────┼──────────────────────────┼───────────────────────────┤
  │ Chargement               │ Automatique (gratuit)    │ Manuel (coûte du contexte)│
  ├──────────────────────────┼──────────────────────────┼───────────────────────────┤
  │ Disponible dès le début  │ Oui                      │ Non                       │
  ├──────────────────────────┼──────────────────────────┼───────────────────────────┤
  │ Globs conditionnels      │ Oui (natif)              │ Non                       │
  ├──────────────────────────┼──────────────────────────┼───────────────────────────┤
  │ Format reconnu           │ Markdown + YAML standard │ Format Cursor (best eff.) │
  ├──────────────────────────┼──────────────────────────┼───────────────────────────┤
  │ Fiabilité                │ 100% (injecté au prompt) │ Variable (dépend du ctx)  │
  ├──────────────────────────┼──────────────────────────┼───────────────────────────┤
  │ Coût en tokens/session   │ ~0 (déjà dans le prompt) │ ~2000-5000 par session    │
  └──────────────────────────┴──────────────────────────┴───────────────────────────┘

### Pourquoi la confusion existe

- Les fichiers `.mdc` ressemblent au Markdown — Claude peut les lire, ce qui donne l'illusion que « ça marche »
- Le nom « .ai-development » suggère un standard universel, mais il n'existe aucun standard inter-outils pour les instructions IA
- Certains tutoriels mélangent les écosystèmes Cursor et Claude Code
- Le fait que Claude arrive à suivre ces instructions **en best effort** masque le coût réel en contexte consommé

### La migration reste simple

1. Lire chaque fichier `.mdc` dans `.ai-development/`
2. Extraire le contenu pertinent
3. Créer un fichier `.md` équivalent dans `.claude/rules/`
4. Adapter le frontmatter : remplacer le format Cursor par le format Claude Code (voir [section 9](#9-frontmatter-et-globs--le-chargement-conditionnel))
5. Supprimer le dossier `.ai-development/` devenu inutile

---

## 6. Architecture recommandée du dossier .claude/

Voici la structure recommandée, issue du retour d'expérience MediCore :

```
.claude/
├── rules/
│   ├── 00-architecture/
│   │   └── 0-elt-pipeline-architecture.md
│   ├── 01-standards/
│   │   ├── 1-clean-code.md
│   │   ├── 1-markdown-standards.md
│   │   ├── 1-naming-conventions.md
│   │   └── 1-python-code-standards.md
│   ├── 02-programming-languages/
│   │   ├── 2-python-advanced.md
│   │   └── 2-sql-dbt-standards.md
│   ├── 03-frameworks-and-libraries/
│   │   ├── 3-dbt-models.md
│   │   ├── 3-kafka-cdc.md
│   │   ├── 3-mysql-connector.md
│   │   └── 3-snowflake-connector.md
│   ├── 04-tools-and-configurations/
│   │   ├── 4-docker-infrastructure.md
│   │   └── 4-project-structure.md
│   ├── 05-workflows-and-processes/
│   │   ├── 5-bug-investigation.md
│   │   └── 5-git-workflow.md
│   ├── 07-quality-assurance/
│   │   └── 7-dbt-testing.md
│   └── 08-domain-specific-rules/
│       ├── 8-cdc-data-integrity.md
│       ├── 8-pharmacy-data-model.md
│       └── 8-pii-masking.md
├── memory-bank/
│   ├── index.md
│   ├── architecture.md
│   ├── data-model.md
│   └── ...
├── rules-index.md
└── settings.local.json
```

### Principes de cette structure

- **Préfixe numérique** (00-, 01-, ...) pour l'ordre de lecture humain
- **Un fichier = un domaine** (pas de fichier fourre-tout)
- **Sous-dossiers par catégorie** (standards, langages, frameworks...)
- **Index centralisé** (`rules-index.md`) pour naviguer rapidement
- **memory-bank/** pour la documentation de référence (non injectée automatiquement, consultée à la demande)

---

## 7. CLAUDE.md — le fichier constitutionnel

Le CLAUDE.md racine est le premier fichier lu par Claude Code. Il doit rester concis (**50 à 100 lignes** recommandées) et contenir :

- :white_check_mark: Vue d'ensemble de l'architecture (3-5 lignes)
- :white_check_mark: Composants clés et leurs chemins
- :white_check_mark: Conventions majeures (langues, nommage, commits)
- :white_check_mark: Commandes essentielles (build, test, deploy)
- :white_check_mark: Règles de sécurité critiques (PII, credentials)
- :white_check_mark: Pointeurs vers les rules et la documentation détaillée

**Ce qu'il ne doit PAS contenir** :

- :x: Des instructions détaillées par technologie → `rules/`
- :x: De la documentation exhaustive → `docs/` ou `memory-bank/`
- :x: Des exemples de code longs → `rules/` avec frontmatter ciblé
- :x: L'historique du projet → `CHANGELOG.md`

> **Analogie** : CLAUDE.md est la **constitution** du projet. Les rules sont les **lois d'application**. La memory-bank est l'**encyclopédie** de référence.

---

## 8. Les Rules — des instructions ciblées et modulaires

Chaque fichier dans `.claude/rules/` est un ensemble d'instructions focalisées sur un domaine :

```yaml
---
description: Brève description du contenu de la règle.
globs: "**/*.py"
---

- Instruction 1
- Instruction 2
- Instruction 3
```

### Avantages par rapport à un fichier unique

  ┌───────────────────┬────────────────────────────────────────────────────────────┐
  │     Avantage      │                        Description                         │
  ├───────────────────┼────────────────────────────────────────────────────────────┤
  │ **Modularité**    │ Modifier une règle dbt n'affecte pas les règles Git        │
  ├───────────────────┼────────────────────────────────────────────────────────────┤
  │ **Lisibilité**    │ Un développeur trouve instantanément la règle pertinente   │
  ├───────────────────┼────────────────────────────────────────────────────────────┤
  │ **Ciblage**       │ Les globs permettent de ne charger que les règles utiles   │
  ├───────────────────┼────────────────────────────────────────────────────────────┤
  │ **Versioning**    │ Le diff Git montre exactement quelle règle a changé        │
  ├───────────────────┼────────────────────────────────────────────────────────────┤
  │ **Collaboration** │ Chaque membre de l'équipe peut proposer des règles         │
  ├───────────────────┼────────────────────────────────────────────────────────────┤
  │ **Scalabilité**   │ 5 ou 50 règles, la structure reste claire                  │
  └───────────────────┴────────────────────────────────────────────────────────────┘

### Budget d'instructions

Claude Code suit de manière fiable environ **100 à 150 instructions** personnalisées. Le prompt système en utilise déjà ~50, ce qui laisse ~100-150 pour le projet. CLAUDE.md et les rules sans frontmatter partagent ce budget. Les rules avec globs ne consomment du budget que lorsqu'elles sont activées.

---

## 9. Frontmatter et globs : le chargement conditionnel

Le frontmatter YAML en tête de chaque rule contrôle quand elle est chargée.

### Sans globs (chargement systématique)

```yaml
---
description: Conventions de nommage.
---
```

- Chargé à **CHAQUE** session, quel que soit le fichier manipulé
- À réserver aux règles universelles (architecture, sécurité...)

### Avec globs (chargement conditionnel)

```yaml
---
description: Règles dbt pour les modèles staging et marts.
globs: "dbt/models/**/*.sql"
---
```

- Chargé **UNIQUEMENT** quand Claude travaille sur des fichiers `.sql` dans `dbt/models/`
- Idéal pour les règles spécifiques à une technologie ou un dossier

### Patterns de globs courants

  ┌────────────────────────┬─────────────────────────────────────────────────┐
  │        Pattern         │                  Correspond à                   │
  ├────────────────────────┼─────────────────────────────────────────────────┤
  │ `**/*.py`              │ Tous les fichiers Python                        │
  ├────────────────────────┼─────────────────────────────────────────────────┤
  │ `**/*.sql`             │ Tous les fichiers SQL                           │
  ├────────────────────────┼─────────────────────────────────────────────────┤
  │ `pipelines/**/*.py`    │ Python dans `pipelines/` uniquement             │
  ├────────────────────────┼─────────────────────────────────────────────────┤
  │ `dbt/models/**/*.sql`  │ SQL dans les modèles dbt                        │
  ├────────────────────────┼─────────────────────────────────────────────────┤
  │ `scripts/**/*.sh`      │ Scripts Bash                                    │
  ├────────────────────────┼─────────────────────────────────────────────────┤
  │ `**/*.md`              │ Tous les fichiers Markdown                      │
  ├────────────────────────┼─────────────────────────────────────────────────┤
  │ `docker-compose.yml`   │ Un fichier spécifique                           │
  ├────────────────────────┼─────────────────────────────────────────────────┤
  │ `"**/*.{ts,tsx}"`      │ TypeScript et TSX (accolades entre guillemets)  │
  └────────────────────────┴─────────────────────────────────────────────────┘

> **ATTENTION** : les patterns commençant par `{` ou `*` sont des indicateurs YAML réservés. Toujours les entourer de **guillemets doubles**.

---

## 10. Hiérarchie de priorité des instructions

Claude Code charge les instructions dans cet ordre, du plus général au plus spécifique (le plus spécifique prévaut en cas de conflit) :

  ┌───┬──────────────────────────────────────────┬────────────────────────┐
  │ # │                 Source                   │         Portée         │
  ├───┼──────────────────────────────────────────┼────────────────────────┤
  │ 1 │ Politique gérée (système)                │ Toute l'organisation   │
  ├───┼──────────────────────────────────────────┼────────────────────────┤
  │ 2 │ `~/.claude/CLAUDE.md`                    │ Tous vos projets       │
  ├───┼──────────────────────────────────────────┼────────────────────────┤
  │ 3 │ `~/.claude/rules/*.md`                   │ Tous vos projets       │
  ├───┼──────────────────────────────────────────┼────────────────────────┤
  │ 4 │ `./CLAUDE.md` (racine projet)            │ Projet (équipe)        │
  ├───┼──────────────────────────────────────────┼────────────────────────┤
  │ 5 │ `./.claude/rules/*.md`                   │ Projet (équipe)        │
  ├───┼──────────────────────────────────────────┼────────────────────────┤
  │ 6 │ `./CLAUDE.local.md`                      │ Vous seul (local)      │
  ├───┼──────────────────────────────────────────┼────────────────────────┤
  │ 7 │ Auto-mémoire (`~/.claude/projects/`)     │ Vous seul (par projet) │
  └───┴──────────────────────────────────────────┴────────────────────────┘

**Points clés** :
- Les rules projet (#5) **prévalent** sur les rules utilisateur (#3)
- `CLAUDE.local.md` (#6) **prévaut** sur tout le reste du projet
- L'auto-mémoire (#7) est gérée automatiquement par Claude Code
- Tout est versionnable **sauf** `.local.md` et l'auto-mémoire

---

## 11. Bonnes pratiques issues du terrain

Ces recommandations sont issues de l'expérience concrète sur MediCore (pipeline ELT, 20+ rules, 18 tables, 6 services Docker) :

### 1. Un fichier = un domaine

Ne pas mélanger les règles dbt et les règles Docker dans le même fichier. Si le titre nécessite « et », c'est probablement deux fichiers.

### 2. Instructions concrètes, pas vagues

- :x: *« Écrire du code propre »*
- :white_check_mark: *« Toujours réutiliser un seul curseur Snowflake par opération de table — ne jamais créer un nouveau curseur dans une boucle »*

### 3. Encoder les erreurs passées

Quand un bug est résolu, ajouter une règle pour ne pas le reproduire. Exemple réel : *« TRUNCATE TABLE ne supprime pas les métadonnées COPY INTO — toujours utiliser FORCE = TRUE après un TRUNCATE. »*

### 4. Utiliser les globs pour économiser le budget

Une règle sur les modèles dbt n'a pas besoin d'être chargée quand Claude modifie un Dockerfile. Le glob `"dbt/**/*.sql"` évite de gaspiller le budget d'instructions.

### 5. Versionner avec Git

Les rules sont du code. Elles méritent des commits atomiques, des revues et un historique. Le diff montre exactement ce qui a changé et pourquoi.

### 6. Garder CLAUDE.md léger

50-100 lignes. Si CLAUDE.md dépasse 150 lignes, extraire les sections détaillées vers des rules dédiées.

### 7. Maintenir un index

Un fichier `rules-index.md` centralise la liste de toutes les rules avec leur glob et leur description. Utile pour l'équipe et pour Claude lui-même.

### 8. Réviser périodiquement

Les rules obsolètes polluent le budget d'instructions. Supprimer celles qui ne sont plus pertinentes.

---

## 12. Résultats concrets observés sur MediCore

### Avant CLAUDE.md et Rules

- Claude redécouvrait l'architecture à chaque session (~5 min perdues)
- Erreurs récurrentes : curseurs Snowflake non fermés, fichiers COPY INTO ignorés après TRUNCATE, processus zombies Docker
- Conventions de nommage incohérentes entre sessions
- Messages de commit en anglais puis en français selon les sessions
- Suggestions de code inadaptées au contexte (ex. : proposer un full refresh dbt alors que c'est interdit sur les modèles incrémentaux)

### Après CLAUDE.md et Rules (20 fichiers, ~150 instructions)

- Connaissance immédiate de l'architecture dès la première interaction
- Zéro récurrence des bugs documentés dans les rules
- Conventions respectées systématiquement (nommage, commits, langue)
- Suggestions contextuelles pertinentes (ex. : propose `FORCE = TRUE` automatiquement après un TRUNCATE)
- Gain estimé : **~30% de temps de session économisé** sur les tâches répétitives de mise en contexte

> Le retour sur investissement est immédiat : le temps passé à rédiger les rules est récupéré dès les 2-3 premières sessions.

---

## 13. Objections courantes et réponses

### « Claude est assez intelligent pour comprendre le code sans instructions. »

Claude comprend le code, mais pas les **décisions**. Pourquoi utiliser `FORCE = TRUE` ? Pourquoi interdire le full refresh ? Pourquoi masquer le nom de la pharmacie en MD5 ? Ces décisions métier et techniques ne sont pas dans le code — elles sont dans les rules.

### « Ça fait trop de fichiers à maintenir. »

20 fichiers de 10 lignes chacun sont plus faciles à maintenir qu'un seul fichier de 200 lignes. Le diff Git est lisible, les modifications sont atomiques, et chaque fichier a un responsable clair. C'est le même principe que le code modulaire.

### « Je mets mes instructions dans .ai-development/, ça marche pareil. »

Techniquement, Claude Code **peut** lire ces fichiers — mais il ne les charge pas automatiquement. À chaque session, il doit les découvrir, les lire un par un et les interpréter en best effort. Cela consomme ~2000-5000 tokens de contexte par session et la fiabilité est variable. Avec `.claude/rules/`, les mêmes instructions sont injectées gratuitement dans le prompt système avant la première interaction. C'est la différence entre chercher un livre dans un entrepôt à chaque visite et l'avoir déjà ouvert sur le bureau. (Voir [section 5](#5-pourquoi-ai-development-nest-pas-performant) pour la comparaison détaillée.)

### « Un seul gros CLAUDE.md suffit, pas besoin de rules. »

Claude Code suit efficacement ~100-150 instructions. Si tout est dans un seul fichier sans ciblage, chaque instruction consomme du budget même quand elle n'est pas pertinente. Les globs permettent de charger uniquement les règles utiles au contexte. C'est la différence entre charger toute une bibliothèque et ouvrir le bon livre.

### « Les conventions de code sont dans le linter, pas besoin de rules. »

Le linter vérifie la syntaxe et le style. Les rules couvrent ce que le linter ne peut pas : choix architecturaux, patterns métier, pièges techniques spécifiques au projet, conventions de documentation, workflow Git, et surtout les erreurs passées à ne pas reproduire.

### « Ça prend trop de temps à mettre en place. »

La mise en place initiale prend 1 à 2 heures pour un projet existant. La maintenance est incrémentale : quand un bug est corrigé, ajouter une ligne dans la rule correspondante prend 30 secondes. Le temps gagné par session (contexte immédiat, pas de ré-explication) rembourse l'investissement en 2-3 sessions.

---

## 14. Limites connues

1. **Frontmatter `paths` ignoré dans les rules utilisateur** (`~/.claude/rules/`)
   - Contournement : utiliser les rules au niveau projet
   - Réf. : [github.com/anthropics/claude-code/issues/21858](https://github.com/anthropics/claude-code/issues/21858)

2. **Globs YAML réservés** : les patterns commençant par `{` ou `*` doivent être entre guillemets doubles
   - Exemple : `globs: "**/*.{ts,tsx}"` (avec guillemets)
   - Réf. : [github.com/anthropics/claude-code/issues/13905](https://github.com/anthropics/claude-code/issues/13905)

3. **Budget d'instructions limité** à ~100-150 instructions personnalisées. Au-delà, Claude peut ignorer certaines directives moins prioritaires
   - Contournement : utiliser les globs pour cibler les rules

4. **Imports récursifs** : les imports `@path` dans CLAUDE.md ont une profondeur maximale de 5 niveaux

5. **Chargement à la demande** : les fichiers CLAUDE.md dans les sous-répertoires ne sont chargés que lorsque Claude lit des fichiers dans ces sous-répertoires (pas au démarrage)

---

## 15. Checklist de mise en place

### Phase 1 — Fondations

- [ ] Créer le dossier `.claude/rules/` avec les sous-dossiers
- [ ] Rédiger `CLAUDE.md` racine (50-100 lignes, vue d'ensemble)
- [ ] Créer 3-5 rules initiales (les plus critiques pour le projet)
- [ ] Ajouter `CLAUDE.local.md` au `.gitignore`
- [ ] Commiter et pousser sur la branche principale

### Phase 2 — Enrichissement

- [ ] Extraire les conventions implicites en rules explicites
- [ ] Documenter les bugs passés comme règles préventives
- [ ] Ajouter les globs pour les rules spécifiques à une technologie
- [ ] Créer un `rules-index.md` pour la navigation
- [ ] Former l'équipe à la structure et aux conventions

### Phase 3 — Maintenance

- [ ] Réviser les rules tous les mois (supprimer les obsolètes)
- [ ] Ajouter une rule à chaque bug résolu
- [ ] Mettre à jour CLAUDE.md quand l'architecture évolue
- [ ] Traiter les rules comme du code (revue, commits atomiques)

### Migration depuis .ai-development/ ou .cursorrules

- [ ] Lister tous les fichiers `.mdc` existants
- [ ] Pour chaque fichier, créer l'équivalent `.md` dans `.claude/rules/`
- [ ] Adapter le frontmatter au format Claude Code
- [ ] Vérifier le chargement (Claude doit citer les rules dans ses réponses quand elles sont pertinentes)
- [ ] Supprimer l'ancien dossier `.ai-development/`

---

## 16. Sources officielles

- [Documentation Claude Code — Mémoire et instructions](https://docs.anthropic.com/en/docs/claude-code/memory)
- [Documentation Claude Code — Paramètres](https://docs.anthropic.com/en/docs/claude-code/settings)
- [Issue GitHub — frontmatter paths ignoré (rules utilisateur)](https://github.com/anthropics/claude-code/issues/21858)
- [Issue GitHub — syntaxe YAML dans les globs](https://github.com/anthropics/claude-code/issues/13905)

---

> *« Les instructions persistantes ne remplacent pas l'intelligence de Claude — elles la dirigent. Sans elles, Claude est un expert amnésique. Avec elles, c'est un membre de l'équipe qui se souvient de tout. »*
