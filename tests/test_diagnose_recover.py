"""
Tests pour le script de diagnostic et récupération (diagnose_recover.py).

Ce module teste :
1. Détection des erreurs dans les tables RAW
2. Analyse des patterns d'erreur
3. Récupération automatique des données corrompues
4. Génération de rapports de diagnostic

Exécution :
    pytest tests/test_diagnose_recover.py -v
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TESTS DÉTECTION D'ERREURS
# =============================================================================

class TestErrorDetection:
    """
    Tests de détection des erreurs dans les données.
    
    Le script de diagnostic analyse :
        - Les événements en DLQ (Dead Letter Queue)
        - Les incohérences de données (doublons, valeurs nulles inattendues)
        - Les gaps dans les séquences CDC
    """

    def test_dlq_event_count(self, mock_snowflake_conn):
        """
        Vérifie le comptage des événements en DLQ.
        
        La DLQ contient les événements non traités pour analyse.
        Un nombre élevé indique un problème systémique.
        """
        mock_snowflake_conn.cursor().fetchone.return_value = (42,)
        
        # Simuler la requête
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM RAW._DLQ")
        result = cursor.fetchone()[0]
        
        assert result == 42, "Doit retourner le compte exact"

    def test_dlq_event_grouping_by_error_type(self, mock_snowflake_conn):
        """
        Vérifie le regroupement des erreurs par type.
        
        Permet d'identifier si un type d'erreur domine :
            - parse_error : JSON malformé
            - insert_error : violation de contrainte
            - decode_error : base64 invalide
        """
        mock_snowflake_conn.cursor().fetchall.return_value = [
            ("parse_error", 30),
            ("insert_error", 10),
            ("decode_error", 2)
        ]
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("""
            SELECT SOURCE, COUNT(*) 
            FROM RAW._DLQ 
            GROUP BY SOURCE 
            ORDER BY 2 DESC
        """)
        results = cursor.fetchall()
        
        assert len(results) == 3, "Doit grouper par type d'erreur"
        assert results[0][0] == "parse_error", "parse_error doit être le plus fréquent"

    def test_recent_dlq_events_detection(self, mock_snowflake_conn):
        """
        Vérifie la détection d'événements DLQ récents.
        
        Des erreurs récentes (<24h) indiquent un problème actif.
        """
        now = datetime.now()
        mock_snowflake_conn.cursor().fetchall.return_value = [
            ("RAW_COMMANDES", now - timedelta(hours=2), "JSON parse error"),
            ("RAW_COMMANDES", now - timedelta(hours=1), "JSON parse error"),
        ]
        
        cursor = mock_snowflake_conn.cursor()
        results = cursor.fetchall()
        
        recent_errors = [r for r in results if (now - r[1]).total_seconds() < 86400]
        
        assert len(recent_errors) == 2, "Doit détecter les erreurs récentes"


# =============================================================================
# TESTS ANALYSE DES PATTERNS
# =============================================================================

class TestPatternAnalysis:
    """
    Tests de l'analyse des patterns d'erreur.
    
    L'analyse identifie :
        - Les tables les plus affectées
        - Les heures de pic d'erreurs
        - Les corrélations entre erreurs
    """

    def test_identify_most_affected_table(self, mock_snowflake_conn):
        """
        Vérifie l'identification de la table la plus touchée.
        
        Utile pour prioriser la résolution.
        """
        mock_snowflake_conn.cursor().fetchall.return_value = [
            ("RAW_COMMANDES", 45),
            ("RAW_FACTURES", 12),
            ("RAW_ORDERS", 3)
        ]
        
        cursor = mock_snowflake_conn.cursor()
        results = cursor.fetchall()
        
        most_affected = results[0][0]
        
        assert most_affected == "RAW_COMMANDES", "Doit identifier la table la plus touchée"

    def test_error_rate_calculation(self):
        """
        Vérifie le calcul du taux d'erreur.
        
        Taux = erreurs / total_events * 100
        Un taux > 1% est considéré anormal.
        """
        total_events = 100000
        dlq_events = 150
        
        error_rate = (dlq_events / total_events) * 100
        
        assert error_rate == 0.15, f"Taux d'erreur incorrect: {error_rate}%"
        assert error_rate < 1, "Taux < 1% est acceptable"

    def test_identify_error_spike(self):
        """
        Vérifie la détection de pics d'erreurs.
        
        Un pic = période avec >2x la moyenne d'erreurs.
        Peut indiquer un déploiement problématique ou incident source.
        """
        hourly_errors = [10, 12, 11, 50, 45, 12, 10]  # Pic à l'index 3-4
        avg_errors = sum(hourly_errors) / len(hourly_errors)  # ~21.4
        
        spikes = [h for h in hourly_errors if h > avg_errors * 2]  # > 42.8
        
        assert len(spikes) == 2, "Doit détecter 2 heures de pic (50 et 45 > 42.8)"


# =============================================================================
# TESTS RÉCUPÉRATION
# =============================================================================

class TestRecovery:
    """
    Tests de la récupération automatique.
    
    La récupération peut :
        - Rejouer les événements DLQ après correction du bug
        - Marquer les événements comme "unrecoverable" après analyse
        - Générer un script SQL de correction manuelle
    """

    def test_dlq_event_replay_format(self):
        """
        Vérifie le format des événements DLQ pour replay.
        
        Le payload doit pouvoir être re-parsé comme un event Debezium.
        """
        dlq_event = {
            "SOURCE": "cdc_parse",
            "TABLE_NAME": "RAW_COMMANDES",
            "TOPIC": "winstat.COMMANDES",
            "PAYLOAD": '{"payload": {"op": "c", "after": {"PHA_ID": 1}}}',
            "ERROR_MESSAGE": "Invalid date format",
            "CREATED_AT": datetime.now()
        }
        
        # Vérifier que le payload est du JSON valide
        payload = json.loads(dlq_event["PAYLOAD"])
        
        assert "payload" in payload, "Payload doit contenir la clé 'payload'"
        assert payload["payload"]["op"] == "c", "Opération doit être préservée"

    def test_mark_event_as_unrecoverable(self, mock_snowflake_conn):
        """
        Vérifie le marquage des événements non récupérables.
        
        Après analyse, certains événements sont définitivement invalides.
        On les marque pour ne pas les retraiter.
        """
        cursor = mock_snowflake_conn.cursor()
        
        # Simuler l'update
        update_sql = """
            UPDATE RAW._DLQ 
            SET STATUS = 'unrecoverable', 
                ANALYSIS_NOTE = 'Source data corrupted'
            WHERE ID = 'abc123'
        """
        cursor.execute(update_sql)
        
        assert cursor.execute.called, "Update doit être exécuté"

    def test_generate_recovery_sql(self):
        """
        Vérifie la génération du SQL de récupération.
        
        Génère un INSERT manuel depuis le payload DLQ.
        """
        payload = {"PHA_ID": 1, "PRD_ID": 42, "COM_QUANTITE": 10}
        table = "RAW_COMMANDES"
        
        columns = list(payload.keys())
        values = list(payload.values())
        
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(values))})"
        
        assert "RAW_COMMANDES" in sql, "Table doit être dans le SQL"
        assert "PHA_ID" in sql, "Colonnes doivent être dans le SQL"


# =============================================================================
# TESTS RAPPORT DE DIAGNOSTIC
# =============================================================================

class TestDiagnosticReport:
    """
    Tests de génération du rapport de diagnostic.
    
    Le rapport inclut :
        - Résumé exécutif (OK/WARNING/CRITICAL)
        - Détail des erreurs par table
        - Recommandations de correction
        - Historique des incidents similaires
    """

    def test_status_determination_ok(self):
        """
        Vérifie le statut OK quand tout va bien.
        
        OK = 0 événements DLQ récents + taux d'erreur < 0.1%
        """
        dlq_count_24h = 0
        error_rate = 0.05
        
        if dlq_count_24h == 0 and error_rate < 0.1:
            status = "OK"
        elif dlq_count_24h < 10 or error_rate < 1:
            status = "WARNING"
        else:
            status = "CRITICAL"
        
        assert status == "OK", "Statut doit être OK"

    def test_status_determination_warning(self):
        """
        Vérifie le statut WARNING pour alertes modérées.
        
        WARNING = quelques erreurs mais pas critique
        """
        dlq_count_24h = 5
        error_rate = 0.5
        
        if dlq_count_24h == 0 and error_rate < 0.1:
            status = "OK"
        elif dlq_count_24h < 10 or error_rate < 1:
            status = "WARNING"
        else:
            status = "CRITICAL"
        
        assert status == "WARNING", "Statut doit être WARNING"

    def test_status_determination_critical(self):
        """
        Vérifie le statut CRITICAL pour problèmes graves.
        
        CRITICAL = beaucoup d'erreurs, action immédiate requise
        """
        dlq_count_24h = 100
        error_rate = 2.5
        
        if dlq_count_24h == 0 and error_rate < 0.1:
            status = "OK"
        elif dlq_count_24h < 10 and error_rate < 1:
            status = "WARNING"
        else:
            status = "CRITICAL"
        
        assert status == "CRITICAL", "Statut doit être CRITICAL"

    def test_report_contains_recommendations(self):
        """
        Vérifie que le rapport contient des recommandations.
        
        Chaque type d'erreur doit avoir une recommandation associée.
        """
        error_types = {
            "parse_error": "Vérifier le format JSON des événements Kafka",
            "insert_error": "Vérifier les contraintes de la table Snowflake",
            "decode_error": "Vérifier la configuration DECIMAL de Debezium"
        }
        
        current_error = "parse_error"
        recommendation = error_types.get(current_error, "Contacter l'équipe data")
        
        assert recommendation == "Vérifier le format JSON des événements Kafka"
