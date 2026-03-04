"""
Tests pour le consumer CDC Kafka → Snowflake (daily_cdc_batch.py).

Ce module teste :
1. Parsing des events Debezium (CREATE, UPDATE, DELETE)
2. Décodage des DECIMAL base64 (format Debezium)
3. Conversion des dates (jours depuis epoch → YYYY-MM-DD)
4. Flush batch avec fallback row-by-row
5. Écriture en Dead Letter Queue (DLQ)

Exécution :
    pytest tests/test_daily_cdc_batch.py -v
    pytest tests/test_daily_cdc_batch.py::test_parse_debezium_create_event -v
"""

import pytest
import json
import base64
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Ajouter le répertoire parent au path pour importer les modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# =============================================================================
# TESTS PARSING DEBEZIUM
# =============================================================================

class TestParseDebeziumEvent:
    """
    Tests du parsing des events Debezium.
    
    Debezium capture les changements MySQL (binlog) et les publie sur Kafka.
    Chaque event contient :
        - op: type d'opération (c=create, u=update, d=delete)
        - before/after: état avant/après modification
        - source: métadonnées (db, table, position binlog)
    """

    def test_parse_debezium_create_event(self, sample_debezium_create_event):
        """
        Vérifie qu'un event CREATE (op='c') est correctement parsé.
        
        Comportement attendu :
            - cdc_operation = 'I' (Insert)
            - Données extraites de payload.after
            - Métadonnées CDC ajoutées (cdc_timestamp, cdc_schema, cdc_table, cdc_lsn)
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        # Créer instance sans connexion Snowflake
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        result = cdc._parse_debezium_event(sample_debezium_create_event)
        
        # Vérifications
        assert result["cdc_operation"] == "I", "CREATE doit mapper vers 'I' (Insert)"
        assert result["PHA_ID"] == 1, "PHA_ID doit être extrait de 'after'"
        assert result["PRD_ID"] == 42, "PRD_ID doit être extrait de 'after'"
        assert result["cdc_table"] == "COMMANDES", "cdc_table doit venir de source.table"
        assert result["cdc_schema"] == "winstat", "cdc_schema doit venir de source.db"
        assert "cdc_timestamp" in result, "cdc_timestamp doit être présent"
        assert "cdc_lsn" in result, "cdc_lsn (position binlog) doit être présent"

    def test_parse_debezium_update_event(self, sample_debezium_update_event):
        """
        Vérifie qu'un event UPDATE (op='u') est correctement parsé.
        
        Comportement attendu :
            - cdc_operation = 'U' (Update)
            - Données extraites de payload.after (nouvelle valeur)
            - payload.before ignoré (ancienne valeur)
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        result = cdc._parse_debezium_event(sample_debezium_update_event)
        
        assert result["cdc_operation"] == "U", "UPDATE doit mapper vers 'U'"
        assert result["COM_QUANTITE"] == 15, "Doit utiliser la nouvelle valeur (after), pas l'ancienne"

    def test_parse_debezium_delete_event(self, sample_debezium_delete_event):
        """
        Vérifie qu'un event DELETE (op='d') est correctement parsé.
        
        Comportement attendu :
            - cdc_operation = 'D' (Delete)
            - Données extraites de payload.before (car after est null)
        
        C'est critique : un DELETE n'a pas de 'after', il faut utiliser 'before'.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        result = cdc._parse_debezium_event(sample_debezium_delete_event)
        
        assert result["cdc_operation"] == "D", "DELETE doit mapper vers 'D'"
        assert result["PHA_ID"] == 1, "Doit utiliser 'before' pour les deletes"
        assert result["COM_QUANTITE"] == 15, "Doit utiliser 'before' pour les deletes"

    def test_parse_debezium_missing_payload_raises_error(self):
        """
        Vérifie qu'un event sans clé 'payload' lève une ValueError.
        
        Protège contre les messages Kafka malformés ou vides.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        invalid_event = {"schema": {}, "no_payload_here": True}
        
        with pytest.raises(ValueError, match="No 'payload' in event"):
            cdc._parse_debezium_event(invalid_event)

    def test_parse_debezium_unknown_operation_raises_error(self):
        """
        Vérifie qu'une opération inconnue (ni c, u, d) lève une ValueError.
        
        Les seules opérations valides sont :
            - c (create)
            - u (update)  
            - d (delete)
            - r (snapshot/read) - Note: pas géré actuellement
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        invalid_event = {
            "payload": {
                "op": "x",  # Opération invalide
                "ts_ms": 1708000000000,
                "after": {"PHA_ID": 1},
                "source": {"db": "winstat", "table": "TEST", "pos": 1}
            }
        }
        
        with pytest.raises(ValueError, match="Unknown op"):
            cdc._parse_debezium_event(invalid_event)


# =============================================================================
# TESTS DÉCODAGE DECIMAL BASE64
# =============================================================================

class TestDecodeDebeziumDecimal:
    """
    Tests du décodage DECIMAL Debezium.
    
    Debezium encode les DECIMAL MySQL en base64 (BYTES logical type).
    Format : valeur entière signée en big-endian, divisée par 10^scale.
    
    Exemple : 12.34 avec scale=2
        → 1234 en entier
        → bytes big-endian
        → base64
    """

    def test_decode_decimal_positive_value(self):
        """
        Vérifie le décodage d'un DECIMAL positif.
        
        Valeur test : 12.34 (scale=2)
            - 1234 en entier
            - b'\\x04\\xd2' en bytes (big-endian)
            - 'BNI=' en base64
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        # 1234 en bytes big-endian = b'\x04\xd2' = base64 'BNI='
        encoded = base64.b64encode(int(1234).to_bytes(2, byteorder='big', signed=True)).decode()
        
        result = cdc._decode_debezium_decimal(encoded, scale=2)
        
        assert result == 12.34, f"Attendu 12.34, obtenu {result}"

    def test_decode_decimal_negative_value(self):
        """
        Vérifie le décodage d'un DECIMAL négatif.
        
        Valeur test : -5.67 (scale=2)
            - -567 en entier signé
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        # -567 en bytes big-endian signé
        encoded = base64.b64encode(int(-567).to_bytes(2, byteorder='big', signed=True)).decode()
        
        result = cdc._decode_debezium_decimal(encoded, scale=2)
        
        assert result == -5.67, f"Attendu -5.67, obtenu {result}"

    def test_decode_decimal_zero(self):
        """
        Vérifie le décodage de zéro.
        
        Cas limite important : 0.00 ne doit pas causer d'erreur.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        # 0 en base64 = 'AAA=' (2 bytes de zéros)
        encoded = base64.b64encode(int(0).to_bytes(2, byteorder='big', signed=True)).decode()
        
        result = cdc._decode_debezium_decimal(encoded, scale=2)
        
        assert result == 0.0, f"Attendu 0.0, obtenu {result}"

    def test_decode_decimal_none_returns_none(self):
        """
        Vérifie que None en entrée retourne None.
        
        Les colonnes DECIMAL peuvent être NULL dans MySQL.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        result = cdc._decode_debezium_decimal(None, scale=2)
        
        assert result is None, "None doit retourner None"

    def test_decode_decimal_non_string_passthrough(self):
        """
        Vérifie qu'une valeur déjà numérique passe sans modification.
        
        Parfois Debezium envoie directement un nombre (selon la config).
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        result = cdc._decode_debezium_decimal(12.34, scale=2)
        
        assert result == 12.34, "Valeur numérique doit passer telle quelle"

    def test_decode_decimal_invalid_base64_returns_original(self):
        """
        Vérifie qu'un base64 invalide retourne la valeur originale.
        
        Protège contre les données corrompues sans crasher le pipeline.
        Un warning doit être loggé.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        invalid_base64 = "not_valid_base64!!!"
        
        result = cdc._decode_debezium_decimal(invalid_base64, scale=2)
        
        # Doit retourner la valeur originale sans crasher
        assert result == invalid_base64, "Base64 invalide doit retourner la valeur originale"


# =============================================================================
# TESTS CONVERSION DATE
# =============================================================================

class TestDateConversion:
    """
    Tests de conversion des dates Debezium.
    
    Debezium encode les DATE MySQL en nombre de jours depuis 1970-01-01.
    Exemple : 2024-01-15 = 19737 jours depuis epoch.
    """

    def test_com_date_int_to_string(self):
        """
        Vérifie la conversion d'une date entière vers string YYYY-MM-DD.
        
        COM_DATE arrive comme int (jours depuis 1970-01-01).
        Doit être convertie en "YYYY-MM-DD" pour Snowflake.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        # 2024-01-15 = 19737 jours depuis 1970-01-01
        days_since_epoch = (datetime(2024, 1, 15) - datetime(1970, 1, 1)).days
        
        event = {
            "payload": {
                "op": "c",
                "ts_ms": 1708000000000,
                "after": {"PHA_ID": 1, "COM_DATE": days_since_epoch},
                "source": {"db": "winstat", "table": "COMMANDES", "pos": 1}
            }
        }
        
        result = cdc._parse_debezium_event(event)
        
        assert result["COM_DATE"] == "2024-01-15", f"Attendu '2024-01-15', obtenu '{result['COM_DATE']}'"

    def test_com_date_string_passthrough(self):
        """
        Vérifie qu'une date déjà en string reste inchangée.
        
        Selon la config Debezium, la date peut arriver déjà formatée.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        event = {
            "payload": {
                "op": "c",
                "ts_ms": 1708000000000,
                "after": {"PHA_ID": 1, "COM_DATE": "2024-01-15"},
                "source": {"db": "winstat", "table": "COMMANDES", "pos": 1}
            }
        }
        
        result = cdc._parse_debezium_event(event)
        
        assert result["COM_DATE"] == "2024-01-15", "Date string doit rester inchangée"


# =============================================================================
# TESTS MÉTADONNÉES CDC
# =============================================================================

class TestCDCMetadata:
    """
    Tests des métadonnées CDC ajoutées aux events.
    
    Chaque event parsé doit contenir :
        - cdc_operation: I/U/D
        - cdc_timestamp: datetime du changement
        - cdc_schema: base de données source
        - cdc_table: table source
        - cdc_lsn: position dans le binlog
    """

    def test_cdc_metadata_fields_present(self, sample_debezium_create_event):
        """
        Vérifie que tous les champs CDC sont présents après parsing.
        
        Ces métadonnées sont essentielles pour :
            - Déduplication (cdc_timestamp)
            - Traçabilité (cdc_lsn, cdc_table)
            - Filtrage des deletes en staging (cdc_operation)
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        result = cdc._parse_debezium_event(sample_debezium_create_event)
        
        required_fields = ["cdc_operation", "cdc_timestamp", "cdc_schema", "cdc_table", "cdc_lsn"]
        
        for field in required_fields:
            assert field in result, f"Champ CDC manquant: {field}"

    def test_cdc_timestamp_is_datetime(self, sample_debezium_create_event):
        """
        Vérifie que cdc_timestamp est un objet datetime Python.
        
        ts_ms de Debezium est en millisecondes, doit être converti.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        
        result = cdc._parse_debezium_event(sample_debezium_create_event)
        
        assert isinstance(result["cdc_timestamp"], datetime), "cdc_timestamp doit être un datetime"


# =============================================================================
# TESTS FLUSH BATCH
# =============================================================================

class TestFlushBatch:
    """
    Tests du flush batch (INSERT groupé dans Snowflake).
    
    Le flush utilise executemany() pour insérer N rows en une requête.
    En cas d'erreur, fallback vers INSERT row-by-row pour identifier
    l'event problématique et l'écrire en DLQ.
    """

    def test_flush_batch_builds_correct_query(self, mock_snowflake_conn):
        """
        Vérifie que la requête INSERT est correctement construite.
        
        Format attendu :
            INSERT INTO RAW_COMMANDES ("PHA_ID", "PRD_ID") VALUES (%s, %s)
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        cdc.sf_cursor = mock_snowflake_conn.cursor()
        
        events = [
            {"PHA_ID": 1, "PRD_ID": 42},
            {"PHA_ID": 2, "PRD_ID": 43}
        ]
        
        cdc._flush_batch("RAW_COMMANDES", events)
        
        # Vérifier que executemany a été appelé
        assert mock_snowflake_conn.cursor().executemany.called, "executemany doit être appelé"
        
        # Vérifier le format de la requête
        call_args = mock_snowflake_conn.cursor().executemany.call_args
        query = call_args[0][0]
        
        assert "INSERT INTO RAW_COMMANDES" in query, "Query doit contenir INSERT INTO"
        assert '"PHA_ID"' in query, "Query doit contenir les colonnes quotées"
        assert "%s" in query, "Query doit contenir les placeholders"

    def test_flush_batch_empty_list_noop(self, mock_snowflake_conn):
        """
        Vérifie qu'une liste vide n'exécute aucune requête.
        
        Évite les erreurs SQL sur INSERT avec 0 rows.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        cdc.sf_cursor = mock_snowflake_conn.cursor()
        
        cdc._flush_batch("RAW_COMMANDES", [])
        
        assert not mock_snowflake_conn.cursor().executemany.called, "Aucune requête pour liste vide"

    def test_flush_batch_executemany_values(self, mock_snowflake_conn):
        """
        Vérifie que executemany reçoit les bonnes valeurs.
        
        Les events dict doivent être convertis en liste de tuples.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        cdc.sf_cursor = mock_snowflake_conn.cursor()
        
        events = [
            {"PHA_ID": 1, "PRD_ID": 42},
            {"PHA_ID": 2, "PRD_ID": 43}
        ]
        
        cdc._flush_batch("RAW_COMMANDES", events)
        
        call_args = mock_snowflake_conn.cursor().executemany.call_args
        values = call_args[0][1]
        
        assert len(values) == 2, "Doit y avoir 2 tuples de valeurs"
        assert values[0] == (1, 42), "Premier tuple incorrect"
        assert values[1] == (2, 43), "Deuxième tuple incorrect"

    def test_flush_batch_fallback_on_executemany_error(self, mock_snowflake_conn):
        """
        Vérifie le fallback row-by-row quand executemany échoue.
        
        Si le batch échoue, on insère row par row pour :
            1. Sauver les rows valides
            2. Identifier les rows invalides
            3. Écrire les invalides en DLQ
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        import snowflake.connector.errors
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        cdc.sf_cursor = mock_snowflake_conn.cursor()
        cdc._write_dlq = Mock()  # Mock la DLQ
        
        # executemany échoue avec une erreur Snowflake
        mock_snowflake_conn.cursor().executemany.side_effect = snowflake.connector.errors.Error("Batch failed")
        # execute (row-by-row) réussit
        mock_snowflake_conn.cursor().execute.return_value = None
        
        events = [{"PHA_ID": 1}, {"PHA_ID": 2}]
        
        cdc._flush_batch("RAW_COMMANDES", events)
        
        # Vérifier que execute a été appelé pour chaque row
        assert mock_snowflake_conn.cursor().execute.call_count == 2, "Fallback doit insérer row par row"

    def test_flush_batch_fallback_writes_dlq_on_row_error(self, mock_snowflake_conn):
        """
        Vérifie que les rows en erreur sont écrites en DLQ.
        
        Scénario : executemany échoue, puis la 2ème row échoue aussi.
        La 2ème row doit être écrite en DLQ.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        import snowflake.connector.errors
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        cdc.sf_cursor = mock_snowflake_conn.cursor()
        cdc._write_dlq = Mock()
        
        # executemany échoue avec une erreur Snowflake
        mock_snowflake_conn.cursor().executemany.side_effect = snowflake.connector.errors.Error("Batch failed")
        # execute : 1ère row OK, 2ème row KO
        mock_snowflake_conn.cursor().execute.side_effect = [None, snowflake.connector.errors.Error("Row 2 invalid")]
        
        events = [{"PHA_ID": 1}, {"PHA_ID": "invalid"}]
        
        cdc._flush_batch("RAW_COMMANDES", events)
        
        # Vérifier que _write_dlq a été appelé pour la row invalide
        assert cdc._write_dlq.called, "DLQ doit être appelé pour la row invalide"
        dlq_call_args = cdc._write_dlq.call_args[0]
        assert dlq_call_args[1] == "RAW_COMMANDES", "Table name doit être passé à DLQ"


# =============================================================================
# TESTS DLQ (DEAD LETTER QUEUE)
# =============================================================================

class TestDLQ:
    """
    Tests de la Dead Letter Queue.
    
    La DLQ stocke les events non traitables pour analyse ultérieure.
    Structure : SOURCE, TABLE_NAME, TOPIC, PAYLOAD (JSON), ERROR_MESSAGE, CREATED_AT
    """

    def test_write_dlq_truncates_long_error(self, mock_snowflake_conn):
        """
        Vérifie que les messages d'erreur > 4000 chars sont tronqués.
        
        La colonne ERROR_MESSAGE est VARCHAR(4000) dans Snowflake.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        cdc.sf_cursor = mock_snowflake_conn.cursor()
        
        long_error = "x" * 5000
        
        cdc._write_dlq("cdc_parse", "RAW_TEST", "topic", {"data": 1}, long_error)
        
        # Vérifier que execute a été appelé
        assert mock_snowflake_conn.cursor().execute.called
        
        # Vérifier que l'erreur est tronquée
        call_args = mock_snowflake_conn.cursor().execute.call_args[0]
        error_in_query = call_args[1][4]  # 5ème paramètre = error_message
        assert len(error_in_query) == 4000, "Erreur doit être tronquée à 4000 chars"

    def test_write_dlq_serializes_payload(self, mock_snowflake_conn):
        """
        Vérifie que le payload est sérialisé en JSON.
        
        Le payload peut contenir des types non-JSON (datetime).
        json.dumps avec default=str doit gérer ces cas.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        cdc.sf_cursor = mock_snowflake_conn.cursor()
        
        payload_with_datetime = {
            "PHA_ID": 1,
            "timestamp": datetime(2024, 1, 15, 12, 30, 0)
        }
        
        cdc._write_dlq("cdc_parse", "RAW_TEST", "topic", payload_with_datetime, "error")
        
        # Ne doit pas lever d'exception
        assert mock_snowflake_conn.cursor().execute.called

    def test_ensure_dlq_creates_table(self, mock_snowflake_conn):
        """
        Vérifie que _ensure_dlq exécute CREATE TABLE IF NOT EXISTS.
        
        La table _DLQ doit être créée au démarrage si elle n'existe pas.
        """
        from pipelines.daily_cdc_batch import MediCoreCDC
        
        cdc = MediCoreCDC.__new__(MediCoreCDC)
        cdc.sf_cursor = mock_snowflake_conn.cursor()
        
        cdc._ensure_dlq()
        
        call_args = mock_snowflake_conn.cursor().execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS _DLQ" in call_args, "Doit créer la table _DLQ"


# =============================================================================
# TESTS CONSUMER BATCH
# =============================================================================

class TestConsumeBatch:
    """
    Tests du consumer Kafka batch.
    
    Le consumer lit les messages Kafka, les accumule en buffers,
    et flush vers Snowflake quand le buffer atteint BATCH_SIZE ou timeout.
    """

    def test_consume_batch_commits_after_flush(self, mock_kafka_consumer, mock_snowflake_conn):
        """
        Vérifie que consumer.commit() est appelé après chaque flush.
        
        CRITIQUE : enable_auto_commit=False, donc commit manuel obligatoire.
        Sans commit, les messages sont relus au prochain run.
        """
        # Ce test nécessite un setup plus complexe avec mock du consumer
        # TODO: Implémenter avec mock complet du flow Kafka
        pass

    def test_consume_batch_flushes_remaining_on_timeout(self):
        """
        Vérifie que les buffers restants sont flushés après timeout Kafka.
        
        Quand consumer_timeout_ms est atteint, la boucle for se termine.
        Les buffers non-vides doivent être flushés avant de quitter.
        """
        # TODO: Implémenter avec mock du timeout Kafka
        pass
