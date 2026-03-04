"""
Fixtures pytest partagées pour les tests MediCore.

Ce fichier contient les fixtures réutilisables par tous les tests :
- Mocks des connexions (Snowflake, MySQL, Kafka)
- Données d'exemple (events Debezium, DataFrames)
- Répertoires temporaires

Les fixtures sont automatiquement découvertes par pytest.
"""

import pytest
import os
import tempfile
from unittest.mock import Mock, MagicMock
from datetime import datetime


# =============================================================================
# FIXTURES CONNEXIONS MOCKÉES
# =============================================================================

@pytest.fixture
def mock_snowflake_conn():
    """
    Connexion Snowflake mockée.
    
    Simule snowflake.connector.connect() sans connexion réelle.
    Le curseur retourne des résultats vides par défaut.
    
    Usage dans les tests:
        def test_exemple(mock_snowflake_conn):
            mock_snowflake_conn.cursor().fetchall.return_value = [("col1", "NUMBER")]
    """
    conn = Mock()
    cursor = Mock()
    conn.cursor.return_value = cursor
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    cursor.description = []
    return conn


@pytest.fixture
def mock_mysql_conn():
    """
    Connexion MySQL mockée.
    
    Simule mysql.connector.connect() sans connexion réelle.
    Le curseur supporte fetchmany() pour simuler le chunking.
    
    Usage dans les tests:
        def test_exemple(mock_mysql_conn):
            mock_mysql_conn.cursor().fetchmany.return_value = [(1, "data")]
    """
    conn = Mock()
    cursor = Mock()
    conn.cursor.return_value = cursor
    cursor.fetchmany.return_value = []
    cursor.fetchall.return_value = []
    cursor.description = [("PHA_ID",), ("PRD_ID",)]
    return conn


@pytest.fixture
def mock_kafka_consumer():
    """
    Consumer Kafka mocké.
    
    Simule KafkaConsumer sans connexion réelle à un broker.
    Itérable pour simuler la consommation de messages.
    
    Usage dans les tests:
        def test_exemple(mock_kafka_consumer):
            mock_kafka_consumer.__iter__.return_value = iter([mock_message])
    """
    consumer = Mock()
    consumer.__iter__ = Mock(return_value=iter([]))
    consumer.commit = Mock()
    consumer.close = Mock()
    return consumer


# =============================================================================
# FIXTURES DONNÉES D'EXEMPLE
# =============================================================================

@pytest.fixture
def sample_debezium_create_event():
    """
    Event Debezium CREATE (op='c') pour la table COMMANDES.
    
    Structure réelle d'un message Kafka produit par Debezium.
    Contient payload.after avec les données de la nouvelle ligne.
    
    Champs:
        - op: 'c' (create)
        - ts_ms: timestamp en millisecondes
        - after: données de la ligne créée
        - source: métadonnées (db, table, pos)
    """
    return {
        "payload": {
            "op": "c",
            "ts_ms": 1708000000000,
            "before": None,
            "after": {
                "PHA_ID": 1,
                "COM_GROI": "CMD001",
                "PRD_ID": 42,
                "COM_QUANTITE": 10,
                "COM_DATE": 19750,  # Jours depuis 1970-01-01
                "COM_PAHTNET": "BNI=",  # 12.34 en base64
                "COM_TAUXREMISE": "AAA=",  # 0.00 en base64
            },
            "source": {
                "db": "winstat",
                "table": "COMMANDES",
                "pos": 12345
            }
        }
    }


@pytest.fixture
def sample_debezium_update_event():
    """
    Event Debezium UPDATE (op='u') pour la table COMMANDES.
    
    Contient payload.before (ancienne valeur) et payload.after (nouvelle valeur).
    Le CDC utilise 'after' pour les updates.
    """
    return {
        "payload": {
            "op": "u",
            "ts_ms": 1708000001000,
            "before": {
                "PHA_ID": 1,
                "PRD_ID": 42,
                "COM_QUANTITE": 10
            },
            "after": {
                "PHA_ID": 1,
                "PRD_ID": 42,
                "COM_QUANTITE": 15  # Quantité modifiée
            },
            "source": {
                "db": "winstat",
                "table": "COMMANDES",
                "pos": 12346
            }
        }
    }


@pytest.fixture
def sample_debezium_delete_event():
    """
    Event Debezium DELETE (op='d') pour la table COMMANDES.
    
    Contient payload.before (ligne supprimée), payload.after est null.
    Le CDC utilise 'before' pour les deletes.
    """
    return {
        "payload": {
            "op": "d",
            "ts_ms": 1708000002000,
            "before": {
                "PHA_ID": 1,
                "PRD_ID": 42,
                "COM_QUANTITE": 15
            },
            "after": None,
            "source": {
                "db": "winstat",
                "table": "COMMANDES",
                "pos": 12347
            }
        }
    }


@pytest.fixture
def sample_dataframe():
    """
    DataFrame pandas exemple pour tests bulk load.
    
    Simule les données extraites de MySQL avant transformation.
    Colonnes typiques de la table COMMANDES.
    """
    import pandas as pd
    return pd.DataFrame({
        "PHA_ID": [1, 1, 2],
        "PRD_ID": [42, 43, 42],
        "COM_QUANTITE": [10, 5, 20],
        "COM_DATE": ["2024-01-15", "2024-01-16", "2024-01-15"]
    })


# =============================================================================
# FIXTURES RÉPERTOIRES TEMPORAIRES
# =============================================================================

@pytest.fixture
def temp_export_dir():
    """
    Répertoire temporaire pour les fichiers Parquet.
    
    Créé avant le test, supprimé automatiquement après.
    Utilisé pour tester la génération de fichiers Parquet.
    
    Usage:
        def test_parquet(temp_export_dir):
            filepath = os.path.join(temp_export_dir, "test.parquet")
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_env_vars(monkeypatch):
    """
    Variables d'environnement mockées pour les connexions.
    
    Configure les variables SNOWFLAKE_*, MYSQL_*, KAFKA_* 
    avec des valeurs de test.
    
    Usage:
        def test_connexion(mock_env_vars):
            # Les variables sont déjà configurées
            pass
    """
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "test_account")
    monkeypatch.setenv("SNOWFLAKE_USER", "test_user")
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "test_password")
    monkeypatch.setenv("MYSQL_HOST", "localhost")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_USER", "test_user")
    monkeypatch.setenv("MYSQL_PASSWORD", "test_password")
    monkeypatch.setenv("MYSQL_DATABASE", "winstat")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
