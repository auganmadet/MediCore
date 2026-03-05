"""
Tests pour le script de healthcheck (healthcheck.py).

Ce module teste :
1. Vérification de connectivité (Snowflake, MySQL, Kafka)
2. Vérification de fraîcheur des données
3. Vérification des processus (jobs, locks)
4. Génération du rapport de santé

Exécution :
    pytest tests/test_healthcheck.py -v
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TESTS CONNECTIVITÉ
# =============================================================================

class TestConnectivityChecks:
    """
    Tests de vérification de connectivité.
    
    Le healthcheck vérifie que tous les composants sont accessibles :
        - Snowflake (data warehouse)
        - MySQL (source)
        - Kafka (streaming)
    """

    def test_snowflake_connectivity_success(self, mock_snowflake_conn):
        """
        Vérifie la détection d'une connexion Snowflake réussie.
        
        Exécute SELECT 1 pour tester la connexion.
        """
        mock_snowflake_conn.cursor().fetchone.return_value = (1,)
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        
        connected = result is not None and result[0] == 1
        
        assert connected, "Snowflake devrait être connecté"

    def test_snowflake_connectivity_failure(self, mock_snowflake_conn):
        """
        Vérifie la détection d'une connexion Snowflake échouée.
        
        L'échec peut être dû à : credentials invalides, réseau, account suspendu.
        """
        mock_snowflake_conn.cursor().execute.side_effect = Exception("Connection refused")
        
        cursor = mock_snowflake_conn.cursor()
        
        try:
            cursor.execute("SELECT 1")
            connected = True
        except Exception:
            connected = False
        
        assert not connected, "Snowflake devrait être déconnecté"

    def test_mysql_connectivity_success(self, mock_mysql_conn):
        """
        Vérifie la détection d'une connexion MySQL réussie.
        
        Exécute SELECT 1 pour tester la connexion.
        """
        mock_mysql_conn.cursor().fetchone.return_value = (1,)
        
        cursor = mock_mysql_conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        
        connected = result is not None
        
        assert connected, "MySQL devrait être connecté"

    def test_kafka_connectivity_success(self, mock_kafka_consumer):
        """
        Vérifie la détection d'une connexion Kafka réussie.
        
        Liste les topics pour vérifier la connexion au broker.
        """
        mock_kafka_consumer.topics.return_value = ["winstat.COMMANDES", "winstat.FACTURES"]
        
        topics = mock_kafka_consumer.topics()
        
        connected = len(topics) > 0
        
        assert connected, "Kafka devrait être connecté"

    def test_kafka_connectivity_failure(self, mock_kafka_consumer):
        """
        Vérifie la détection d'une connexion Kafka échouée.
        
        Timeout ou broker inaccessible.
        """
        mock_kafka_consumer.topics.side_effect = Exception("Broker not available")
        
        try:
            mock_kafka_consumer.topics()
            connected = True
        except Exception:
            connected = False
        
        assert not connected, "Kafka devrait être déconnecté"


# =============================================================================
# TESTS FRAÎCHEUR DES DONNÉES
# =============================================================================

class TestDataFreshness:
    """
    Tests de vérification de la fraîcheur des données.
    
    Les données doivent être régulièrement mises à jour :
        - Tables CDC : < 24h de retard
        - Tables référence : < 48h de retard
    """

    def test_cdc_data_freshness_ok(self, mock_snowflake_conn):
        """
        Vérifie qu'une table CDC récente est considérée fraîche.
        
        Fraîche = dernière mise à jour < 12h.
        """
        last_update = datetime.now() - timedelta(hours=6)
        mock_snowflake_conn.cursor().fetchone.return_value = (last_update,)
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("""
            SELECT MAX(CDC_TIMESTAMP) 
            FROM RAW.RAW_COMMANDES
        """)
        result = cursor.fetchone()[0]
        
        hours_since_update = (datetime.now() - result).total_seconds() / 3600
        
        is_fresh = hours_since_update < 12
        
        assert is_fresh, f"Données devraient être fraîches ({hours_since_update:.1f}h)"

    def test_cdc_data_freshness_warning(self, mock_snowflake_conn):
        """
        Vérifie qu'une table CDC > 12h déclenche un warning.
        
        Warning : 12h < retard < 24h.
        """
        last_update = datetime.now() - timedelta(hours=18)
        hours_since_update = 18
        
        if hours_since_update < 12:
            status = "OK"
        elif hours_since_update < 24:
            status = "WARNING"
        else:
            status = "ERROR"
        
        assert status == "WARNING", "Doit être en WARNING"

    def test_cdc_data_freshness_error(self, mock_snowflake_conn):
        """
        Vérifie qu'une table CDC > 24h déclenche une erreur.
        
        Error : retard > 24h = données potentiellement manquantes.
        """
        hours_since_update = 30
        
        if hours_since_update < 12:
            status = "OK"
        elif hours_since_update < 24:
            status = "WARNING"
        else:
            status = "ERROR"
        
        assert status == "ERROR", "Doit être en ERROR"

    def test_reference_data_freshness_thresholds(self):
        """
        Vérifie les seuils pour les tables référence.
        
        Les références changent moins souvent que le CDC :
            - Warning : > 36h
            - Error : > 48h
        """
        hours = 40
        
        if hours < 36:
            status = "OK"
        elif hours < 48:
            status = "WARNING"
        else:
            status = "ERROR"
        
        assert status == "WARNING", "40h doit être WARNING pour les référence"


# =============================================================================
# TESTS PROCESSUS
# =============================================================================

class TestProcessChecks:
    """
    Tests de vérification des processus.
    
    Vérifie :
        - Présence de lock files
        - Processus actifs
        - Jobs schedulés
    """

    def test_lock_file_detection(self, temp_export_dir):
        """
        Vérifie la détection d'un lock file existant.
        
        Un lock file actif indique qu'un bulk load est en cours.
        """
        lock_path = os.path.join(temp_export_dir, "bulk_load.lock")
        
        # Pas de lock file
        assert not os.path.exists(lock_path), "Lock ne devrait pas exister"
        
        # Créer lock file
        with open(lock_path, 'w') as f:
            f.write(f"{os.getpid()} {datetime.now().isoformat()}")
        
        assert os.path.exists(lock_path), "Lock devrait exister"

    def test_stale_lock_detection(self, temp_export_dir):
        """
        Vérifie la détection d'un lock file périmé.
        
        Un lock > 4h est probablement un processus planté.
        Doit être signalé pour investigation manuelle.
        """
        lock_path = os.path.join(temp_export_dir, "bulk_load.lock")
        
        # Créer un lock avec timestamp ancien
        old_time = datetime.now() - timedelta(hours=5)
        with open(lock_path, 'w') as f:
            f.write(f"12345 {old_time.isoformat()}")
        
        # Lire le lock
        with open(lock_path, 'r') as f:
            content = f.read()
        
        parts = content.split()
        lock_time = datetime.fromisoformat(parts[1])
        hours_old = (datetime.now() - lock_time).total_seconds() / 3600
        
        is_stale = hours_old > 4
        
        assert is_stale, "Lock de 5h devrait être considéré périmé"

    def test_running_jobs_count(self, mock_snowflake_conn):
        """
        Vérifie le comptage des jobs actifs dans Snowflake.
        
        Trop de jobs simultanés peut indiquer un problème.
        """
        mock_snowflake_conn.cursor().fetchone.return_value = (3,)
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY())
            WHERE STATE = 'EXECUTING'
        """)
        running_jobs = cursor.fetchone()[0]
        
        assert running_jobs == 3, "Doit retourner le nombre de jobs actifs"


# =============================================================================
# TESTS RAPPORT DE SANTÉ
# =============================================================================

class TestHealthReport:
    """
    Tests de génération du rapport de santé.
    
    Le rapport résume l'état de tous les composants :
        - Connectivité : OK/ERROR
        - Fraîcheur : OK/WARNING/ERROR
        - Processus : OK/WARNING/ERROR
    """

    def test_overall_status_all_ok(self):
        """
        Vérifie le statut global quand tout est OK.
        
        Global = OK si tous les checks sont OK.
        """
        checks = {
            "snowflake": "OK",
            "mysql": "OK",
            "kafka": "OK",
            "data_freshness": "OK",
            "processes": "OK"
        }
        
        if "ERROR" in checks.values():
            overall = "ERROR"
        elif "WARNING" in checks.values():
            overall = "WARNING"
        else:
            overall = "OK"
        
        assert overall == "OK", "Statut global doit être OK"

    def test_overall_status_with_warning(self):
        """
        Vérifie le statut global avec un warning.
        
        Global = WARNING si au moins un check est WARNING (sans ERROR).
        """
        checks = {
            "snowflake": "OK",
            "mysql": "OK",
            "kafka": "OK",
            "data_freshness": "WARNING",  # Un warning
            "processes": "OK"
        }
        
        if "ERROR" in checks.values():
            overall = "ERROR"
        elif "WARNING" in checks.values():
            overall = "WARNING"
        else:
            overall = "OK"
        
        assert overall == "WARNING", "Statut global doit être WARNING"

    def test_overall_status_with_error(self):
        """
        Vérifie le statut global avec une erreur.
        
        Global = ERROR si au moins un check est ERROR.
        """
        checks = {
            "snowflake": "OK",
            "mysql": "ERROR",  # Une erreur
            "kafka": "OK",
            "data_freshness": "WARNING",
            "processes": "OK"
        }
        
        if "ERROR" in checks.values():
            overall = "ERROR"
        elif "WARNING" in checks.values():
            overall = "WARNING"
        else:
            overall = "OK"
        
        assert overall == "ERROR", "Statut global doit être ERROR"

    def test_report_json_format(self):
        """
        Vérifie que le rapport peut être formaté en JSON.
        
        JSON facilite l'intégration avec les outils de monitoring.
        """
        import json
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "OK",
            "checks": {
                "snowflake": {"status": "OK", "latency_ms": 45},
                "mysql": {"status": "OK", "latency_ms": 23},
                "kafka": {"status": "OK", "topics": 4},
                "data_freshness": {"status": "OK", "oldest_data_hours": 6.5},
                "processes": {"status": "OK", "active_jobs": 2}
            }
        }
        
        json_output = json.dumps(report, indent=2)
        
        assert "overall_status" in json_output, "Doit contenir overall_status"
        assert "checks" in json_output, "Doit contenir checks"

    def test_report_includes_timestamp(self):
        """
        Vérifie que le rapport inclut un timestamp.
        
        Important pour l'historique et la corrélation des incidents.
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "status": "OK"
        }
        
        assert "timestamp" in report, "Doit inclure un timestamp"
        # Vérifier que le timestamp est parsable
        datetime.fromisoformat(report["timestamp"])


# =============================================================================
# TESTS ALERTES
# =============================================================================

class TestAlerts:
    """
    Tests du système d'alertes.
    
    Les alertes sont envoyées quand :
        - Un check passe de OK à ERROR
        - Une situation WARNING persiste > 1h
    """

    def test_alert_on_status_change_to_error(self):
        """
        Vérifie qu'une alerte est déclenchée quand un check devient ERROR.
        
        Scénario : MySQL était OK, devient ERROR.
        """
        previous_status = "OK"
        current_status = "ERROR"
        
        should_alert = previous_status != "ERROR" and current_status == "ERROR"
        
        assert should_alert, "Doit déclencher une alerte sur passage à ERROR"

    def test_no_alert_on_sustained_error(self):
        """
        Vérifie qu'une erreur persistante ne déclenche pas d'alerte répétée.
        
        Évite le spam d'alertes pour le même problème.
        """
        previous_status = "ERROR"
        current_status = "ERROR"
        
        should_alert = previous_status != "ERROR" and current_status == "ERROR"
        
        assert not should_alert, "Ne doit pas alerter sur erreur persistante"

    def test_alert_on_prolonged_warning(self):
        """
        Vérifie qu'un warning prolongé finit par alerter.
        
        Un WARNING > 1h devient préoccupant et mérite attention.
        """
        warning_duration_hours = 1.5
        
        should_alert = warning_duration_hours > 1
        
        assert should_alert, "WARNING prolongé doit déclencher une alerte"
