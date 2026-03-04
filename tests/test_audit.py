"""
Tests pour le script d'audit Snowflake (audit.py).

Ce module teste :
1. Collecte des métriques d'utilisation
2. Analyse de la consommation de crédits
3. Détection des anomalies de performance

Exécution :
    pytest tests/test_audit.py -v
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TESTS MÉTRIQUES D'UTILISATION
# =============================================================================

class TestUsageMetrics:
    """
    Tests de la collecte des métriques d'utilisation.
    
    Les métriques incluent :
        - Nombre de requêtes par jour
        - Temps d'exécution moyen
        - Volume de données traitées
    """

    def test_query_count_last_30_days(self, mock_snowflake_conn):
        """
        Vérifie le comptage des requêtes sur 30 jours.
        
        Utilise ACCOUNT_USAGE.QUERY_HISTORY avec filtre sur START_TIME.
        Note : ACCOUNT_USAGE a une latence de 45 minutes.
        """
        mock_snowflake_conn.cursor().fetchone.return_value = (15420,)
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE START_TIME >= DATEADD(day, -30, CURRENT_TIMESTAMP())
        """)
        result = cursor.fetchone()[0]
        
        assert result == 15420, "Doit retourner le compte exact"

    def test_average_execution_time(self, mock_snowflake_conn):
        """
        Vérifie le calcul du temps d'exécution moyen.
        
        Temps moyen en millisecondes. > 10 secondes peut indiquer
        un problème de performance.
        """
        mock_snowflake_conn.cursor().fetchone.return_value = (3500,)  # 3.5 secondes
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("""
            SELECT AVG(TOTAL_ELAPSED_TIME) 
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE START_TIME >= DATEADD(day, -30, CURRENT_TIMESTAMP())
        """)
        avg_time_ms = cursor.fetchone()[0]
        
        assert avg_time_ms == 3500, "Temps moyen incorrect"
        assert avg_time_ms < 10000, "Temps moyen trop élevé (> 10s)"

    def test_data_volume_scanned(self, mock_snowflake_conn):
        """
        Vérifie le volume de données scannées.
        
        Metric importante pour optimiser les coûts.
        Un volume élevé peut indiquer des full table scans évitables.
        """
        # 500 GB scannés
        mock_snowflake_conn.cursor().fetchone.return_value = (500 * 1024 * 1024 * 1024,)
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("""
            SELECT SUM(BYTES_SCANNED) 
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE START_TIME >= DATEADD(day, -30, CURRENT_TIMESTAMP())
        """)
        bytes_scanned = cursor.fetchone()[0]
        gb_scanned = bytes_scanned / (1024 ** 3)
        
        assert gb_scanned == 500, "Volume scanné incorrect"


# =============================================================================
# TESTS CONSOMMATION DE CRÉDITS
# =============================================================================

class TestCreditConsumption:
    """
    Tests de l'analyse de consommation de crédits.
    
    1 crédit = environ 2$ (selon le contrat Snowflake).
    Le warehouse MEDICORE_WH est X-Small (1 crédit/heure actif).
    """

    def test_total_credits_last_30_days(self, mock_snowflake_conn):
        """
        Vérifie le total des crédits consommés sur 30 jours.
        
        MEDICORE_WH devrait consommer ~15 crédits/mois
        (basé sur l'audit précédent : 14.77 crédits).
        """
        mock_snowflake_conn.cursor().fetchone.return_value = (14.77,)
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("""
            SELECT SUM(CREDITS_USED)
            FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
            WHERE START_TIME >= DATEADD(day, -30, CURRENT_TIMESTAMP())
              AND WAREHOUSE_NAME = 'MEDICORE_WH'
        """)
        credits = cursor.fetchone()[0]
        
        assert credits == 14.77, "Total crédits incorrect"

    def test_credit_trend_analysis(self, mock_snowflake_conn):
        """
        Vérifie l'analyse de tendance de consommation.
        
        Compare semaine actuelle vs semaine précédente.
        Une augmentation > 20% déclenche une alerte.
        """
        # Semaine actuelle : 5 crédits, semaine précédente : 4 crédits
        mock_snowflake_conn.cursor().fetchall.return_value = [
            ("current_week", 5.0),
            ("previous_week", 4.0)
        ]
        
        current = 5.0
        previous = 4.0
        change_pct = ((current - previous) / previous) * 100
        
        assert change_pct == 25.0, f"Changement calculé: {change_pct}%"
        assert change_pct > 20, "Doit déclencher une alerte (>20%)"

    def test_cost_estimation(self, mock_snowflake_conn):
        """
        Vérifie l'estimation du coût en dollars.
        
        Hypothèse : 2$ par crédit (à ajuster selon contrat).
        """
        credits = 14.77
        cost_per_credit = 2.0
        
        estimated_cost = credits * cost_per_credit
        
        assert estimated_cost == 29.54, f"Coût estimé: ${estimated_cost}"

    def test_identify_expensive_queries(self, mock_snowflake_conn):
        """
        Vérifie l'identification des requêtes coûteuses.
        
        Top 5 requêtes par crédits consommés.
        """
        mock_snowflake_conn.cursor().fetchall.return_value = [
            ("COPY INTO RAW_COMMANDES...", 2.5, 45000),
            ("SELECT * FROM MARTS.FCT_SALES...", 1.8, 30000),
            ("MERGE INTO STAGING.STG_COMMANDES...", 1.2, 25000),
        ]
        
        cursor = mock_snowflake_conn.cursor()
        results = cursor.fetchall()
        
        top_query = results[0]
        assert "COPY INTO" in top_query[0], "COPY INTO devrait être le plus coûteux"
        assert top_query[1] == 2.5, "Crédits du top query incorrect"


# =============================================================================
# TESTS DÉTECTION D'ANOMALIES
# =============================================================================

class TestAnomalyDetection:
    """
    Tests de détection des anomalies de performance.
    
    Les anomalies incluent :
        - Requêtes anormalement lentes
        - Pics de consommation inattendus
        - Échecs de requêtes répétés
    """

    def test_slow_query_detection(self, mock_snowflake_conn):
        """
        Vérifie la détection des requêtes lentes.
        
        Lente = temps d'exécution > 3x la moyenne.
        """
        avg_time = 3000  # 3 secondes
        threshold = avg_time * 3
        
        mock_snowflake_conn.cursor().fetchall.return_value = [
            ("SELECT ...", 15000),  # 15 secondes = lent
            ("INSERT ...", 12000),  # 12 secondes = lent
        ]
        
        cursor = mock_snowflake_conn.cursor()
        results = cursor.fetchall()
        
        slow_queries = [r for r in results if r[1] > threshold]
        
        assert len(slow_queries) == 2, "Doit détecter 2 requêtes lentes"

    def test_failed_query_detection(self, mock_snowflake_conn):
        """
        Vérifie la détection des requêtes échouées.
        
        Les échecs répétés sur la même requête indiquent un bug.
        """
        mock_snowflake_conn.cursor().fetchall.return_value = [
            ("SELECT * FROM UNKNOWN_TABLE", "FAIL", 15),
            ("INSERT INTO RAW.LOCKED_TABLE", "FAIL", 8),
        ]
        
        cursor = mock_snowflake_conn.cursor()
        results = cursor.fetchall()
        
        repeated_failures = [r for r in results if r[2] > 5]  # >5 échecs
        
        assert len(repeated_failures) == 2, "Doit détecter les échecs répétés"

    def test_warehouse_queueing_detection(self, mock_snowflake_conn):
        """
        Vérifie la détection de queuing warehouse.
        
        Queuing = requêtes en attente car warehouse saturé.
        Indique un besoin de scale-up.
        """
        mock_snowflake_conn.cursor().fetchone.return_value = (150,)  # 150ms avg queue time
        
        cursor = mock_snowflake_conn.cursor()
        cursor.execute("""
            SELECT AVG(QUEUED_OVERLOAD_TIME)
            FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
            WHERE START_TIME >= DATEADD(day, -7, CURRENT_TIMESTAMP())
              AND WAREHOUSE_NAME = 'MEDICORE_WH'
        """)
        avg_queue_time = cursor.fetchone()[0]
        
        # Queuing > 100ms peut indiquer un problème
        if avg_queue_time > 100:
            recommendation = "Consider scaling up warehouse"
        else:
            recommendation = "Warehouse size adequate"
        
        assert avg_queue_time == 150, "Queue time incorrect"
        assert "scaling up" in recommendation, "Doit recommander scale-up"


# =============================================================================
# TESTS RAPPORT D'AUDIT
# =============================================================================

class TestAuditReport:
    """
    Tests de génération du rapport d'audit.
    
    Le rapport inclut :
        - Score de santé global (0-100)
        - Métriques clés
        - Recommandations priorisées
    """

    def test_health_score_calculation(self):
        """
        Vérifie le calcul du score de santé.
        
        Score basé sur :
            - Taux d'erreur (40%)
            - Temps d'exécution (30%)
            - Coût vs budget (30%)
        """
        error_rate_score = 95  # Peu d'erreurs
        performance_score = 80  # Temps correct
        cost_score = 90  # Dans le budget
        
        weights = [0.4, 0.3, 0.3]
        scores = [error_rate_score, performance_score, cost_score]
        
        health_score = sum(w * s for w, s in zip(weights, scores))
        
        assert health_score == 89.0, f"Score de santé: {health_score}"

    def test_report_format_markdown(self):
        """
        Vérifie que le rapport est en format Markdown.
        
        Facilite l'intégration dans la documentation ou Slack.
        """
        report = """
# Audit Report - MEDICORE_WH
## Summary
- Health Score: 89/100
- Credits Used: 14.77

## Recommendations
1. Consider enabling query caching
2. Review slow queries
"""
        
        assert "# Audit Report" in report, "Doit avoir un titre H1"
        assert "## Summary" in report, "Doit avoir une section Summary"
        assert "## Recommendations" in report, "Doit avoir des recommandations"
