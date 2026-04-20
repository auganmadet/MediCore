# MediCore - Pipeline ELT Pharmacie

Pipeline ELT industrialisé : MySQL RDS → Kafka CDC → Snowflake RAW → dbt (STG/MARTS).
18 tables (4 CDC + 14 référence), monitoring Teams webhook, source freshness.

## Table des matières

1. [Prérequis](#prérequis)
   - [Docker Desktop](#1-docker-desktop)
   - [SnowSQL CLI](#2-snowsql-cli)
   - [jq](#3-jq-json-processor)
   - [Configuration snowsql](#4-configuration-snowsql)
   - [Fichier .env](#5-fichier-env)
   - [Vérification complète](#6-vérification-complète-des-prérequis)
   - [Durées estimées](#durées-estimées)
2. [Architecture](#architecture)
3. [Structure du projet](#structure-du-projet)
4. [Installation](#installation)
5. [Accès web](#accès-web)
6. [Fonctionnement](#fonctionnement)
7. [Monitoring](#monitoring)

---

## Prérequis

### 1. Docker Desktop

**Windows** (PowerShell Admin) :
```powershell
# Télécharger et installer Docker Desktop
winget install Docker.DockerDesktop

# Redémarrer le PC, puis vérifier
docker --version
docker compose version
```

**Linux (Ubuntu/Debian)** :
```bash
# Installer Docker
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Ajouter l'utilisateur au groupe docker (évite sudo)
sudo usermod -aG docker $USER
newgrp docker

# Vérifier
docker --version
docker compose version
```

**macOS** :
```bash
brew install --cask docker
# Lancer Docker Desktop depuis Applications
docker --version
```

---

### 2. SnowSQL CLI

**Windows** (PowerShell Admin) :
```powershell
# Télécharger l'installeur
Invoke-WebRequest -Uri "https://sfc-repo.snowflakecomputing.com/snowsql/bootstrap/1.2/windows_x86_64/snowsql-1.2.32-windows_x86_64.msi" -OutFile "$env:TEMP\snowsql.msi"

# Installer silencieusement
msiexec /i "$env:TEMP\snowsql.msi" /qn

# Ajouter au PATH (redémarrer le terminal après)
# Le chemin par défaut est : C:\Users\<user>\AppData\Local\Snowflake\SnowSQL

# Vérifier
snowsql --version
```

**Linux/macOS** :
```bash
# Télécharger et installer
curl -O https://sfc-repo.snowflakecomputing.com/snowsql/bootstrap/1.2/linux_x86_64/snowsql-1.2.32-linux_x86_64.bash
bash snowsql-1.2.32-linux_x86_64.bash

# Vérifier
snowsql --version
```

---

### 3. jq (JSON processor)

**Windows (Git Bash)** :
```bash
mkdir -p ~/bin
curl -L -o ~/bin/jq.exe https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-win64.exe
chmod +x ~/bin/jq.exe
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Vérifier
jq --version
```

**Windows (PowerShell)** :
```powershell
winget install jqlang.jq
# ou
choco install jq

# Vérifier
jq --version
```

**Linux** :
```bash
sudo apt-get install -y jq
jq --version
```

**macOS** :
```bash
brew install jq
jq --version
```

---

### 4. Configuration snowsql

Créer/éditer `~/.snowsql/config` :

**Windows** : `%USERPROFILE%\.snowsql\config`
**Linux/macOS** : `~/.snowsql/config`

```ini
# Connexion ADMIN (pour setup.sh --with-snowflake-ddl uniquement)
[connections.medicore_admin]
accountname = YMYUNAB-HR05962
username = <votre_user>
authenticator = snowflake
password = <votre_password>
warehousename = MEDICORE_WH
database = MEDICORE
schemaname = RAW
rolename = ACCOUNTADMIN

# Connexion opérationnelle (pour reset, vérifications, etc.)
[connections.medicore]
accountname = YMYUNAB-HR05962
username = <votre_user>
authenticator = snowflake
password = <votre_password>
warehousename = MEDICORE_WH
database = MEDICORE
schemaname = RAW
rolename = MEDICORE_RAW_WRITER
```

Tester les connexions :
```bash
snowsql -c medicore_admin -q "SELECT CURRENT_ROLE();"
snowsql -c medicore -q "SELECT CURRENT_ROLE();"
```

---

### 5. Fichier .env

```bash
cp .env.example .env
# Éditer .env avec vos credentials MySQL RDS, Snowflake, Teams webhook
```

---

### 6. Vérification complète des prérequis

```bash
# Tout doit retourner une version
docker --version           # Docker version 24.x+
docker compose version     # Docker Compose version v2.20+
snowsql --version          # SnowSQL 1.2.x
jq --version               # jq-1.6+

# Tester connexion Snowflake
snowsql -c medicore_admin -q "SELECT 'OK' AS status;"
```

---

### Durées estimées

  ┌─────────────────────────────┬───────────────┬───────────────────────────────────────────┐
  │           Phase             │   Durée       │                 Détails                   │
  ├─────────────────────────────┼───────────────┼───────────────────────────────────────────┤
  │ DDL Snowflake               │ ~30s          │ Création DB, schemas, rôles, tables       │
  ├─────────────────────────────┼───────────────┼───────────────────────────────────────────┤
  │ Docker stack                │ ~3 min        │ Build image + démarrage 6 services        │
  ├─────────────────────────────┼───────────────┼───────────────────────────────────────────┤
  │ Debezium connector          │ ~1 min        │ Connexion RDS + schema_only snapshot      │
  ├─────────────────────────────┼───────────────┼───────────────────────────────────────────┤
  │ **Bulk load (920M lignes)** │ **45-90 min** │ MySQL → Parquet → COPY INTO RAW           │
  ├─────────────────────────────┼───────────────┼───────────────────────────────────────────┤
  │ **Total setup initial**     │ **~50-95 min**│ Dépend de la bande passante réseau        │
  └─────────────────────────────┴───────────────┴───────────────────────────────────────────┘

[↑ Retour au sommaire](#table-des-matières)

---

## Architecture

Voir [Architecture détaillée](docs/01_ARCHITECTURE.md) pour les schémas complets (flux, services Docker, monitoring).

[↑ Retour au sommaire](#table-des-matières)

---

## Structure du projet

```
MediCore/
├── docker-compose.yml                  # 7 services (ELT, MySQL, Kafka, Zookeeper, Connect, Kafdrop, dbt_docs)
├── Dockerfile                          # Image medicore_elt_batch
├── requirements.txt                    # Dépendances Python
├── .env                                # Variables d'environnement (non versionné)
│
├── pipelines/
│   ├── daily_cdc_batch.py              # Consumer Kafka → INSERT RAW (4 tables CDC)
│   ├── bulk_load.py                    # MySQL SELECT → Parquet → COPY INTO RAW (18 tables)
│   └── utils/
│       └── pii_masking.py              # Masquage PII (utilisé par dbt staging)
│
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── packages.yml                    # dbt_utils
│   ├── models/
│   │   ├── sources.yml                 # 18 sources RAW + freshness (4 CDC + 14 réf)
│   │   ├── staging/
│   │   │   ├── _staging.yml            # Tests staging
│   │   │   └── stg_*.sql              # 18 modèles staging (dédup CDC + PII masking)
│   │   └── marts/
│   │       ├── _marts.yml              # Tests marts
│   │       ├── dim_*.sql              # 3 dimensions (produit, fournisseur, pharmacie)
│   │       └── fact_*.sql             # 8 faits (ventes, commandes, stock, ruptures...)
│   └── macros/
│       └── pii_masking.sql
│
├── scripts/
│   ├── setup.sh                        # Premier lancement (HOST : DDL + Docker + Debezium)
│   ├── entrypoint.sh                   # Démarrage container (wait deps + dbt deps + batch)
│   ├── batch_loop.sh                   # Boucle principale (CDC + dbt + tests + freshness + alertes)
│   ├── verify_setup.sh                 # Vérification post-setup (Docker, Kafka, Snowflake, dbt)
│   ├── reset_and_bulk_load.sh          # Reset CDC + bulk load (quick ou full)
│   ├── healthcheck.py                  # Docker HEALTHCHECK (connexion Snowflake)
│   ├── DDL_WH.sql                      # Warehouse, rôles, grants Snowflake
│   └── DDL_TABLES.sql                  # 18 tables RAW + CLUSTER BY
│
└── docs/
    ├── 01_ARCHITECTURE.md                 # Vue d'ensemble (flux, services Docker, monitoring)
    ├── 02_workflow_multi_env.md            # Environnements (DEV/TEST/PROD) et CI/CD
    ├── 03_operations.md                   # Orchestration batch et monitoring
    ├── 04_strategie_orchestration_batch.md # Détail stratégie batch (fréquences, mode nuit)
    ├── 05_KPIs.md                         # KPIs métier (formules, grain, utilités)
    ├── 06_Dashboards.md                   # Guide utilisateur Metabase
    ├── 07_guide_provisionnement_metabase.md # Setup et provisionnement Metabase
    ├── 08_procedure_rollback.md           # Procédure rollback prod (Time Travel)
    ├── 09_rotation_credentials.md         # Rotation trimestrielle des credentials
    ├── 10_guide-claude-code-rules.md      # Guide Claude Code (rules, memory-bank)
    └── 11_disaster_recovery.md            # Plan de reprise d'activité (DR)
```

[↑ Retour au sommaire](#table-des-matières)

---

## Installation

```bash
# 1. Configurer .env (voir section Prérequis)
cp .env.example .env
# Éditer .env avec vos credentials

# 2. Premier lancement (DDL Snowflake + Docker + bulk load)
#    Durée : ~50-95 min (920M lignes)
bash scripts/setup.sh --with-snowflake-ddl

# 3. Vérifier que tout est opérationnel
bash scripts/verify_setup.sh
```

**Note** : Le premier run dbt (staging + marts) démarre automatiquement via `batch_loop.sh` dès que le bulk load est terminé. Pas d'action manuelle requise.

Voir [Workflow multi-environnement](docs/02_workflow_multi_env.md) pour comprendre les 3 environnements (DEV/TEST/PROD) créés par le setup.

[↑ Retour au sommaire](#table-des-matières)

---

## Accès web

  ┌───────────────────────────┬──────────┬────────────────────────────────────────────────────┐
  │ Service                   │ Port     │ URL                                                │
  ├───────────────────────────┼──────────┼────────────────────────────────────────────────────┤
  │ Metabase (BI dashboards)  │ 3000     │ http://localhost:3000                              │
  ├───────────────────────────┼──────────┼────────────────────────────────────────────────────┤
  │ Data Catalog (dbt docs)   │ 8080     │ http://localhost:8080                              │
  ├───────────────────────────┼──────────┼────────────────────────────────────────────────────┤
  │ Kafdrop (Kafka UI)        │ 9000     │ http://localhost:9000                              │
  └───────────────────────────┴──────────┴────────────────────────────────────────────────────┘

Voir [Opérations — Data Catalog](docs/03_operations.md#data-catalog-dbt-docs) pour la configuration réseau (pare-feu, portproxy WSL2).

[↑ Retour au sommaire](#table-des-matières)

---

## Fonctionnement

Le conteneur `medicore_elt_batch` exécute `batch_loop.sh` en boucle (5 min dev / 30 min prod) :

1. **Re-bulk référence** (1x/jour à 23h FR) : `bulk_load.py --ref-only --truncate` (14 tables, CLONE+SWAP)
2. **CDC** : `daily_cdc_batch.py` consomme les events Kafka (4 tables)
3. **dbt staging** : `dbt run --select tag:staging` (dédup + PII masking)
4. **dbt marts** : `dbt run --select tag:marts` (dims + facts)
5. **dbt test** : `dbt test --select stg_*` (not_null, unique, relationships)
6. **Source freshness** : `dbt source freshness` (détecte données stales)

Voir [Opérations](docs/03_operations.md) et [Stratégie d'orchestration batch](docs/04_strategie_orchestration_batch.md) pour le détail complet.

[↑ Retour au sommaire](#table-des-matières)

---

## Monitoring

- **Teams webhook** : alertes échec/recovery sur chaque phase (seuil configurable)
- **Source freshness** : CDC warn 12h / error 24h, référence warn 36h / error 48h
- **Docker healthcheck** : tous les services avec healthcheck + depends_on condition
- **Resource limits** : mem_limit + cpus sur les 6 conteneurs

Voir [Opérations](docs/03_operations.md) pour le détail du monitoring, des alertes et des procédures de diagnostic.

[↑ Retour au sommaire](#table-des-matières)
