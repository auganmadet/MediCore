#!/bin/bash
# ==============================================================================
# SCRIPT : run_all_tests.sh
# PROJET : MediCore ELT Pipeline
# AUTEUR : Équipe Data Engineering
# DATE   : 2026-03-04
# ==============================================================================
# USAGE (avec durée de temps)
# ---------------------------
# BASH   cd /mnt/c/Temp/MediCore && STARTTIME=$(date +%s) && ./scripts/run_all_tests.sh 2>&1; echo "=== Durée totale: $(($(date +%s) -
#  STARTTIME)) secondes ==="
#
# DESCRIPTION
# -----------
# Script d'exécution complète des tests du pipeline MediCore.
# Ce script valide l'intégrité de bout en bout du flux de données :
#   MySQL (source) → Debezium CDC → Kafka → Consumer Python → Snowflake RAW → dbt → MARTS
#
# PRÉREQUIS
# ---------
# 1. Docker Compose démarré : docker compose up -d
# 2. Variables d'environnement définies dans .env :
#    - MYSQL_ROOT_PASSWORD : Mot de passe root MySQL
#    - SNOWFLAKE_ACCOUNT   : Compte Snowflake (ex: xy12345.eu-west-1)
#    - SNOWFLAKE_USER      : Utilisateur Snowflake
#    - SNOWFLAKE_PASSWORD  : Mot de passe Snowflake
# 3. Connecteur Debezium configuré et actif
# 4. Python avec dépendances installées (snowflake-connector-python, kafka-python)
#
# ÉTAPES DU SCRIPT
# ----------------
# 1. PYTEST        : Tests unitaires Python (mocks, pas d'infra requise)
# 2. BULK LOAD     : Chargement initial MySQL → Snowflake RAW (18 tables)
# 3. CDC INSERT    : Test création d'enregistrement via CDC Debezium
# 4. CDC UPDATE    : Test modification d'enregistrement via CDC Debezium
# 5. CDC DELETE    : Test suppression d'enregistrement via CDC Debezium
# 6. DBT BUILD     : Transformations dbt (STAGING + MARTS) + tests qualité
#
# DONNÉES DE TEST CDC
# -------------------
# Le script utilise des IDs fictifs élevés pour éviter les conflits :
#   - PHA_ID     = 99999       (Pharmacie fictive)
#   - COM_GROI   = 999999999   (Numéro commande fictif)
#   - PRD_ID     = 888888      (Produit fictif)
#
# Ces données sont automatiquement nettoyées à la fin du script.
#
# VÉRIFICATIONS AUTOMATIQUES
# --------------------------
# Pour chaque opération CDC, le script :
#   1. Exécute l'opération dans MySQL (INSERT/UPDATE/DELETE)
#   2. Attend la propagation Debezium vers Kafka (5 secondes)
#   3. Lance le consumer CDC pour ingérer dans Snowflake RAW
#   4. Interroge Snowflake pour vérifier :
#      - cdc_operation = 'C' (Create), 'U' (Update), ou 'D' (Delete)
#      - Valeurs des colonnes modifiées
#   5. Affiche PASS ou FAIL selon le résultat
#
# UTILISATION
# -----------
#   chmod +x scripts/run_all_tests.sh
#   ./scripts/run_all_tests.sh
#
# CODES DE SORTIE
# ---------------
#   0 : Tous les tests passés
#   1 : Au moins un test échoué (le script s'arrête au premier échec)
#
# ==============================================================================

set -e  # Arrête le script à la première erreur

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Configuration MySQL (RDS ou Docker)
# Si MYSQL_HOST contient 'rds.amazonaws.com', on utilise le client mysql local
# Sinon, on utilise docker exec pour accéder au conteneur
MYSQL_CONTAINER="mysql"

# Données de test (IDs élevés pour éviter conflits avec données réelles)
TEST_PHA_ID=99999           # ID Pharmacie fictif
TEST_COM_GROI=999999999     # Numéro de commande fictif
TEST_PRD_ID=888888          # ID Produit fictif

# Délai d'attente pour la propagation Debezium (secondes)
CDC_PROPAGATION_DELAY=5

# Timeout du consumer CDC (secondes)
CDC_CONSUMER_TIMEOUT=30

# Répertoire racine du projet (parent du répertoire scripts/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Activer l'environnement virtuel Python si présent
if [[ -f "$PROJECT_ROOT/.venv/bin/activate" ]]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
elif [[ -f "$PROJECT_ROOT/.venv/Scripts/activate" ]]; then
    source "$PROJECT_ROOT/.venv/Scripts/activate"
fi

# ==============================================================================
# FONCTIONS UTILITAIRES
# ==============================================================================

# Affiche un titre d'étape formaté
log_step() {
    echo ""
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

# Affiche un message de succès
log_pass() {
    echo "✓ PASS : $1"
}

# Affiche un message d'échec et arrête le script
log_fail() {
    echo "✗ FAIL : $1"
    echo ""
    echo "Le script s'arrête suite à cet échec."
    echo "Consultez les logs ci-dessus pour diagnostiquer le problème."
    exit 1
}

# Affiche une information
log_info() {
    echo "  → $1"
}

# ------------------------------------------------------------------------------
# mysql_exec : Exécute une requête SQL sur MySQL (via Python)
# 
# Usage : mysql_exec "SELECT * FROM table;"
# 
# Pour les tests CDC, on utilise le MySQL local Docker (mysql_cdc) car c'est
# celui surveillé par Debezium. Le MySQL RDS n'est pas connecté à Debezium.
# ------------------------------------------------------------------------------
mysql_exec() {
    local query="$1"
    python3 -c "
import mysql.connector

# Pour les tests CDC, utiliser MySQL local Docker (surveillé par Debezium)
# Le conteneur mysql_cdc expose le port 3307 sur localhost
MYSQL_CDC_HOST = 'localhost'
MYSQL_CDC_PORT = 3307
MYSQL_CDC_USER = 'root'
MYSQL_CDC_PASSWORD = 'debezium'
MYSQL_CDC_DATABASE = 'winstat'

try:
    conn = mysql.connector.connect(
        host=MYSQL_CDC_HOST,
        port=MYSQL_CDC_PORT,
        user=MYSQL_CDC_USER,
        password=MYSQL_CDC_PASSWORD,
        database=MYSQL_CDC_DATABASE
    )
    cursor = conn.cursor()
    cursor.execute('''$query''')
    conn.commit()
    print('OK')
    conn.close()
except Exception as e:
    print(f'ERROR:{e}')
    exit(1)
"
}

# ------------------------------------------------------------------------------
# ensure_commandes_table : Crée la table COMMANDES si elle n'existe pas
# ------------------------------------------------------------------------------
ensure_commandes_table() {
    python3 -c "
import mysql.connector

conn = mysql.connector.connect(
    host='localhost',
    port=3307,
    user='root',
    password='debezium',
    database='winstat'
)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS COMMANDES (
    PHA_ID INT NOT NULL,
    COM_GROI BIGINT NOT NULL,
    PRD_ID INT NOT NULL,
    COM_GROS INT NOT NULL,
    COM_DATE DATE NOT NULL,
    FOU_ID VARCHAR(16),
    COM_QUANTITE INT NOT NULL,
    COM_PAHTNET DECIMAL(8,2),
    COM_TAUXREMISE DECIMAL(6,2),
    PRIMARY KEY (PHA_ID, COM_GROI, PRD_ID)
)
''')
conn.commit()
print('OK')
conn.close()
"
}

# ------------------------------------------------------------------------------
# snowflake_query : Exécute une requête Snowflake et retourne le résultat
# 
# Usage : result=$(snowflake_query "SELECT col1, col2 FROM table;")
# 
# Retourne les colonnes séparées par '|' (pipe)
# Retourne 'NO_RESULT' si aucune ligne trouvée
# 
# Cette fonction crée une connexion Python temporaire à Snowflake
# en utilisant les variables d'environnement SNOWFLAKE_*.
# ------------------------------------------------------------------------------
snowflake_query() {
    local query="$1"
    python3 -c "
import snowflake.connector
import os

try:
    conn = snowflake.connector.connect(
        account=os.environ['SNOWFLAKE_ACCOUNT'],
        user=os.environ['SNOWFLAKE_USER'],
        password=os.environ['SNOWFLAKE_PASSWORD'],
        warehouse='MEDICORE_WH',
        database='MEDICORE',
        schema='RAW'
    )
    cursor = conn.cursor()
    cursor.execute('''$query''')
    row = cursor.fetchone()
    if row:
        print('|'.join(str(x) if x is not None else 'NULL' for x in row))
    else:
        print('NO_RESULT')
    conn.close()
except Exception as e:
    print(f'ERROR:{e}')
"
}

# ==============================================================================
# VÉRIFICATION DES PRÉREQUIS
# ==============================================================================

log_step "0/6 Vérification des prérequis"

# Vérifier que les variables d'environnement sont définies
if [[ -z "$MYSQL_PASSWORD" ]]; then
    # Tenter de charger depuis .env
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        log_info "Chargement des variables depuis .env"
        export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
    fi
fi

# Vérifier les variables requises
for var in MYSQL_HOST MYSQL_USER MYSQL_PASSWORD MYSQL_DATABASE SNOWFLAKE_ACCOUNT SNOWFLAKE_USER SNOWFLAKE_PASSWORD; do
    if [[ -z "${!var}" ]]; then
        log_fail "Variable d'environnement $var non définie. Vérifiez votre fichier .env"
    fi
done
log_pass "Variables d'environnement OK"

# Vérifier que Docker est accessible (seulement si MySQL n'est pas sur RDS)
if [[ "$MYSQL_HOST" != *"rds.amazonaws.com"* ]] && [[ "$MYSQL_HOST" != *"amazonaws.com"* ]]; then
    if ! docker ps > /dev/null 2>&1; then
        log_fail "Docker n'est pas accessible. Vérifiez que Docker Desktop est démarré."
    fi
    log_pass "Docker accessible"

    # Vérifier que le conteneur MySQL est actif
    if ! docker ps --format '{{.Names}}' | grep -q "^${MYSQL_CONTAINER}$"; then
        log_fail "Conteneur MySQL '$MYSQL_CONTAINER' non trouvé. Lancez 'docker compose up -d'"
    fi
    log_pass "Conteneur MySQL actif"
else
    log_info "MySQL sur RDS : $MYSQL_HOST"
    log_pass "Connexion RDS configurée"
fi

# ==============================================================================
# ÉTAPE 1 : TESTS UNITAIRES PYTEST
# ==============================================================================
# 
# Les tests pytest vérifient la logique du code Python sans infrastructure.
# Ils utilisent des mocks pour simuler Kafka, MySQL et Snowflake.
# 
# Fichiers testés :
#   - tests/test_daily_cdc_batch.py : Consumer CDC Kafka
#   - tests/test_bulk_load.py       : Chargement bulk MySQL → Snowflake
# ==============================================================================

log_step "1/6 Tests unitaires pytest"

cd "$PROJECT_ROOT"
log_info "Exécution de pytest tests/ -v"

if pytest tests/ -v; then
    log_pass "Tous les tests unitaires passés"
else
    log_fail "Échec des tests unitaires pytest"
fi

# ==============================================================================
# ÉTAPE 2 : BULK LOAD MySQL → Snowflake RAW (DÉSACTIVÉ)
# ==============================================================================
# 
# Le bulk load extrait les 18 tables de référence depuis MySQL
# et les charge dans Snowflake RAW via des fichiers Parquet.
# 
# Tables chargées : DAYBYDAY, EAN13, FOURNISSEURS, HISTORY, LOG, LPPR,
#                   OPERATEUR, PHARMACIE, PRODUITS, QUANTHEB, REMISE,
#                   STOCK, TRESORERIE, VENTEPRD, etc.
# 
# NOTE : Cette étape est désactivée car les 18 tables sont déjà chargées.
#        Le bulk load prend plusieurs heures et n'est pas nécessaire pour
#        les tests CDC quotidiens. Décommenter uniquement pour un rechargement
#        complet initial.
# ==============================================================================

# log_step "2/6 Bulk load MySQL → Snowflake RAW"
# 
# cd "$PROJECT_ROOT"
# log_info "Exécution de python pipelines/bulk_load.py"
# 
# if python pipelines/bulk_load.py; then
#     log_pass "Bulk load terminé avec succès"
# else
#     log_fail "Échec du bulk load"
# fi

log_step "2/6 Bulk load MySQL → Snowflake RAW (IGNORÉ)"
log_info "Étape désactivée - Les 18 tables sont déjà chargées dans Snowflake RAW"
log_pass "Bulk load ignoré (données déjà présentes)"

# ==============================================================================
# ÉTAPE 3 : TEST CDC - INSERT
# ==============================================================================
# 
# Ce test vérifie que l'insertion d'un enregistrement dans MySQL
# est correctement capturée par Debezium et propagée vers Snowflake.
# 
# Flux : MySQL INSERT → Debezium → Kafka → Consumer → Snowflake RAW
# 
# Vérification : cdc_operation = 'C' (Create)
# ==============================================================================

log_step "3/6 Test CDC - INSERT (Create)"

# S'assurer que la table COMMANDES existe dans MySQL Docker (idempotence)
log_info "Vérification/création de la table COMMANDES dans MySQL Docker"
ensure_commandes_table

# Nettoyer les données de test existantes dans MySQL (au cas où un test précédent a échoué)
log_info "Nettoyage préalable des données de test dans MySQL"
mysql_exec "DELETE FROM COMMANDES WHERE PHA_ID = $TEST_PHA_ID AND COM_GROI = $TEST_COM_GROI;" 2>/dev/null || true

# Nettoyer les données de test existantes dans Snowflake (idempotence)
log_info "Nettoyage préalable des données de test dans Snowflake RAW"
snowflake_query "DELETE FROM RAW_COMMANDES WHERE PHA_ID = $TEST_PHA_ID AND COM_GROI = $TEST_COM_GROI;" >/dev/null 2>&1 || true

# Exécuter l'INSERT dans MySQL
log_info "INSERT dans MySQL : PHA_ID=$TEST_PHA_ID, COM_GROI=$TEST_COM_GROI, PRD_ID=$TEST_PRD_ID"
mysql_exec "
INSERT INTO COMMANDES (
    PHA_ID, COM_GROI, PRD_ID, COM_GROS, COM_DATE,
    FOU_ID, COM_QUANTITE, COM_PAHTNET, COM_TAUXREMISE
) VALUES (
    $TEST_PHA_ID, $TEST_COM_GROI, $TEST_PRD_ID, 1, CURDATE(),
    'TEST_FOU', 10, 25.50, 5.00
);
"

# Attendre la propagation Debezium vers Kafka
log_info "Attente de ${CDC_PROPAGATION_DELAY}s pour propagation Debezium..."
sleep $CDC_PROPAGATION_DELAY

# Lancer le consumer CDC pour ingérer les événements Kafka dans Snowflake
log_info "Exécution du consumer CDC (timeout=${CDC_CONSUMER_TIMEOUT}s)"
cd "$PROJECT_ROOT"
CDC_KAFKA_TOPIC_PREFIX=winstat.winstat KAFKA_BOOTSTRAP_SERVERS=localhost:9092 CDC_BATCH_TIMEOUT_SEC=$CDC_CONSUMER_TIMEOUT python pipelines/daily_cdc_batch.py 2>&1 || true

# Vérifier dans Snowflake que l'INSERT a été capturé
log_info "Vérification dans Snowflake RAW..."
RESULT=$(snowflake_query "
SELECT cdc_operation, COM_QUANTITE, COM_PAHTNET
FROM RAW_COMMANDES
WHERE PHA_ID = $TEST_PHA_ID AND COM_GROI = $TEST_COM_GROI
ORDER BY cdc_timestamp DESC
LIMIT 1;
")

log_info "Résultat Snowflake : $RESULT"

# Valider le résultat (cdc_operation=I, quantité=10, prix=25.50)
if [[ "$RESULT" == "I|10|25.5"* ]] || [[ "$RESULT" == "I|10|25.50"* ]]; then
    log_pass "CDC INSERT vérifié (cdc_operation='I', COM_QUANTITE=10, COM_PAHTNET=25.50)"
else
    log_fail "CDC INSERT incorrect - Attendu: I|10|25.50, Reçu: $RESULT"
fi

# ==============================================================================
# ÉTAPE 4 : TEST CDC - UPDATE
# ==============================================================================
# 
# Ce test vérifie que la modification d'un enregistrement dans MySQL
# est correctement capturée par Debezium et propagée vers Snowflake.
# 
# Modification : COM_QUANTITE 10→20, COM_PAHTNET 25.50→45.00
# 
# Vérification : cdc_operation = 'U' (Update)
# ==============================================================================

log_step "4/6 Test CDC - UPDATE"

# Exécuter l'UPDATE dans MySQL
log_info "UPDATE dans MySQL : COM_QUANTITE=20, COM_PAHTNET=45.00"
mysql_exec "
UPDATE COMMANDES
SET COM_QUANTITE = 20,
    COM_PAHTNET = 45.00,
    COM_TAUXREMISE = 10.00
WHERE PHA_ID = $TEST_PHA_ID
  AND COM_GROI = $TEST_COM_GROI
  AND PRD_ID = $TEST_PRD_ID;
"

# Attendre la propagation Debezium vers Kafka
log_info "Attente de ${CDC_PROPAGATION_DELAY}s pour propagation Debezium..."
sleep $CDC_PROPAGATION_DELAY

# Lancer le consumer CDC
log_info "Exécution du consumer CDC (timeout=${CDC_CONSUMER_TIMEOUT}s)"
cd "$PROJECT_ROOT"
CDC_KAFKA_TOPIC_PREFIX=winstat.winstat KAFKA_BOOTSTRAP_SERVERS=localhost:9092 CDC_BATCH_TIMEOUT_SEC=$CDC_CONSUMER_TIMEOUT python pipelines/daily_cdc_batch.py 2>&1 || true

# Vérifier dans Snowflake que l'UPDATE a été capturé
log_info "Vérification dans Snowflake RAW..."
RESULT=$(snowflake_query "
SELECT cdc_operation, COM_QUANTITE, COM_PAHTNET
FROM RAW_COMMANDES
WHERE PHA_ID = $TEST_PHA_ID AND COM_GROI = $TEST_COM_GROI
ORDER BY cdc_timestamp DESC
LIMIT 1;
")

log_info "Résultat Snowflake : $RESULT"

# Valider le résultat (cdc_operation=U, quantité=20, prix=45.00)
if [[ "$RESULT" == "U|20|45"* ]] || [[ "$RESULT" == "U|20|45.0"* ]] || [[ "$RESULT" == "U|20|45.00"* ]]; then
    log_pass "CDC UPDATE vérifié (cdc_operation='U', COM_QUANTITE=20, COM_PAHTNET=45.00)"
else
    log_fail "CDC UPDATE incorrect - Attendu: U|20|45.00, Reçu: $RESULT"
fi

# ==============================================================================
# ÉTAPE 5 : TEST CDC - DELETE
# ==============================================================================
# 
# Ce test vérifie que la suppression d'un enregistrement dans MySQL
# est correctement capturée par Debezium et propagée vers Snowflake.
# 
# Note : Dans le pattern CDC, les DELETE ne suppriment pas physiquement
# les données de RAW, ils ajoutent une ligne avec cdc_operation='D'.
# La suppression logique est gérée dans la couche STAGING (WHERE cdc_operation != 'D').
# 
# Vérification : cdc_operation = 'D' (Delete)
# ==============================================================================

log_step "5/6 Test CDC - DELETE"

# Exécuter le DELETE dans MySQL
log_info "DELETE dans MySQL : PHA_ID=$TEST_PHA_ID, COM_GROI=$TEST_COM_GROI"
mysql_exec "
DELETE FROM COMMANDES
WHERE PHA_ID = $TEST_PHA_ID
  AND COM_GROI = $TEST_COM_GROI
  AND PRD_ID = $TEST_PRD_ID;
"

# Attendre la propagation Debezium vers Kafka
log_info "Attente de ${CDC_PROPAGATION_DELAY}s pour propagation Debezium..."
sleep $CDC_PROPAGATION_DELAY

# Lancer le consumer CDC
log_info "Exécution du consumer CDC (timeout=${CDC_CONSUMER_TIMEOUT}s)"
cd "$PROJECT_ROOT"
CDC_KAFKA_TOPIC_PREFIX=winstat.winstat KAFKA_BOOTSTRAP_SERVERS=localhost:9092 CDC_BATCH_TIMEOUT_SEC=$CDC_CONSUMER_TIMEOUT python pipelines/daily_cdc_batch.py 2>&1 || true

# Vérifier dans Snowflake que le DELETE a été capturé
log_info "Vérification dans Snowflake RAW..."
RESULT=$(snowflake_query "
SELECT cdc_operation
FROM RAW_COMMANDES
WHERE PHA_ID = $TEST_PHA_ID AND COM_GROI = $TEST_COM_GROI
ORDER BY cdc_timestamp DESC
LIMIT 1;
")

log_info "Résultat Snowflake : $RESULT"

# Valider le résultat (cdc_operation=D)
if [[ "$RESULT" == "D"* ]]; then
    log_pass "CDC DELETE vérifié (cdc_operation='D')"
else
    log_fail "CDC DELETE incorrect - Attendu: D, Reçu: $RESULT"
fi

# ==============================================================================
# ÉTAPE 6 : DBT BUILD (Transformations + Tests qualité)
# ==============================================================================
# 
# dbt build exécute dans l'ordre :
#   1. dbt run  : Transformations SQL (RAW → STAGING → MARTS)
#   2. dbt test : Tests de qualité des données (not_null, unique, relationships)
# 
# Modèles exécutés :
#   - STAGING : 18 modèles stg_* (déduplication CDC, masquage PII)
#   - MARTS   : 3 dimensions + 8 faits + 9 KPIs
# ==============================================================================

log_step "6/6 dbt build (Transformations + Tests qualité)"

cd "$PROJECT_ROOT/dbt"
log_info "Exécution de dbt build"

# Utiliser un répertoire temporaire pour éviter les problèmes de permissions WSL
export DBT_TARGET_PATH="/tmp/dbt_target_$$"
mkdir -p "$DBT_TARGET_PATH"

# Capturer la sortie dbt pour analyser les erreurs
DBT_OUTPUT=$("$PROJECT_ROOT/.venv/bin/dbt" build --profiles-dir "$PROJECT_ROOT/dbt" --target-path "$DBT_TARGET_PATH" 2>&1)
DBT_EXIT_CODE=$?

# Afficher la sortie (filtrer les warnings de dépréciation)
echo "$DBT_OUTPUT" | grep -v "Deprecat"

# Extraire le résumé (ligne "Done. PASS=X WARN=Y ERROR=Z")
DBT_SUMMARY=$(echo "$DBT_OUTPUT" | grep -oE "Done\. PASS=[0-9]+ WARN=[0-9]+ ERROR=[0-9]+" | tail -1)
DBT_ERROR_COUNT=$(echo "$DBT_SUMMARY" | grep -oE "ERROR=[0-9]+" | grep -oE "[0-9]+")

# Vérifier les erreurs
if [ -n "$DBT_ERROR_COUNT" ] && [ "$DBT_ERROR_COUNT" -gt 0 ]; then
    log_fail "dbt build a terminé avec $DBT_ERROR_COUNT erreur(s) - $DBT_SUMMARY"
elif [ $DBT_EXIT_CODE -ne 0 ]; then
    log_fail "dbt build a échoué (exit code: $DBT_EXIT_CODE)"
else
    log_pass "dbt build terminé avec succès - $DBT_SUMMARY"
fi

# Nettoyage du répertoire temporaire
rm -rf "$DBT_TARGET_PATH" 2>/dev/null

# ==============================================================================
# NETTOYAGE DES DONNÉES DE TEST
# ==============================================================================
# 
# Suppression des enregistrements de test dans Snowflake RAW
# pour ne pas polluer les données de production.
# ==============================================================================

log_step "Nettoyage des données de test"

log_info "Suppression des données de test dans Snowflake RAW..."
CLEANUP_RESULT=$(snowflake_query "
DELETE FROM RAW_COMMANDES
WHERE PHA_ID = $TEST_PHA_ID AND COM_GROI = $TEST_COM_GROI;
SELECT 'CLEANED';
")

if [[ "$CLEANUP_RESULT" == *"CLEANED"* ]] || [[ "$CLEANUP_RESULT" == *"NO_RESULT"* ]]; then
    log_pass "Données de test supprimées de Snowflake"
else
    log_info "Note: Nettoyage Snowflake peut nécessiter une vérification manuelle"
fi

# ==============================================================================
# RÉSUMÉ FINAL
# ==============================================================================

echo ""
echo "============================================================"
echo "         ✓ TOUS LES TESTS PASSÉS AVEC SUCCÈS"
echo "============================================================"
echo ""
echo "  Récapitulatif des tests :"
echo "  ─────────────────────────────────────────────────────────"
echo "  1. pytest (tests unitaires)     : ✓ PASS"
echo "  2. bulk_load (MySQL → RAW)      : ✓ SKIP (déjà chargé)"
echo "  3. CDC INSERT (cdc_operation=I) : ✓ PASS"
echo "  4. CDC UPDATE (cdc_operation=U) : ✓ PASS"
echo "  5. CDC DELETE (cdc_operation=D) : ✓ PASS"
echo "  6. dbt build (STAGING + MARTS)  : ✓ PASS"
echo "  ─────────────────────────────────────────────────────────"
echo ""
echo "  Le pipeline MediCore est opérationnel de bout en bout."
echo ""
echo "============================================================"

exit 0
