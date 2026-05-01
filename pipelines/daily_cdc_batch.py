#!/usr/bin/env python3
"""
Debezium se connecte à MySQL et publie les évènements binlog sur Kafka (topics)
Lit les événements Debezium sur Kafka + traite les nouveautés + écrit RAW_* avec métadonnées CDC dans Snowflake
daily_cdc_batch est appelé par batch_loop.sh

PII masking : non appliqué ici (RAW = données brutes).
Le masquage est effectué dans les modèles dbt STAGING (stg_orders, stg_pharmacie, etc.)
"""

import base64
import json
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import snowflake.connector
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Micro-batch : accumule N events ou attend TIMEOUT avant flush
BATCH_SIZE = 500
BATCH_TIMEOUT_SEC = int(os.getenv('CDC_BATCH_TIMEOUT_SEC', '30'))

# Topics Kafka Debezium (prefix.TABLE pour chaque table CDC)
CDC_KAFKA_TOPIC_PREFIX = os.getenv('CDC_KAFKA_TOPIC_PREFIX', 'winstat_rds.winstat')
CDC_KAFKA_GROUP_ID = os.getenv('CDC_KAFKA_GROUP_ID', 'medi_core_cdc_batch_dev2')
CDC_TABLES_KAFKA = ['COMMANDES', 'FACTURES', 'ORDERS', 'MODSTOCK']

# Circuit-breaker : arreter le fallback row-by-row si N rows consecutifs echouent
# (erreur systemique comme un mismatch schema, pas un event individuel toxique)
FALLBACK_MAX_CONSECUTIVE_FAILS = int(os.getenv('CDC_FALLBACK_MAX_FAILS', '10'))

# Codes d'erreur Snowflake indiquant qu'une reconnexion est necessaire
SNOWFLAKE_AUTH_EXPIRED_CODES = (390114, 390116, 390111)  # token expired / session expired

# Mapping DECIMAL columns par table CDC (decoder Base64 Debezium)
# Extrait depuis MySQL INFORMATION_SCHEMA : SELECT COLUMN_NAME, NUMERIC_SCALE
# WHERE DATA_TYPE = 'decimal'
CDC_DECIMAL_COLUMNS: Dict[str, Dict[str, int]] = {
    'COMMANDES': {'COM_PAHTNET': 2, 'COM_TAUXREMISE': 2},
    'FACTURES': {'FAC_TVA': 2, 'FAC_PAHT': 2, 'FAC_PVHT': 2, 'FAC_PVTTC': 2,
                 'FAC_PRIXPUBLIC': 2, 'FAC_REMISE': 2},
    'ORDERS': {'ORD_TOTAL_GENERAL': 2, 'ORD_TOTAL_REMB_SS': 2, 'ORD_TOTAL_REMB_MUTU': 2},
    'MODSTOCK': {},
}

# Mapping DATE/DATETIME columns par table CDC
# Debezium encode :
#   - MySQL DATE     -> int en JOURS depuis 1970-01-01 (io.debezium.time.Date)
#   - MySQL DATETIME -> int en MILLISECONDES depuis 1970-01-01 (io.debezium.time.Timestamp)
# Snowflake attend DATE ou TIMESTAMP_NTZ, il faut donc convertir les int en datetime.
CDC_DATE_COLUMNS: Dict[str, Dict[str, str]] = {
    'COMMANDES': {'COM_DATE': 'date'},
    'FACTURES': {'FAC_DATE': 'datetime'},
    'ORDERS': {'ORD_DATE': 'datetime', 'ORD_DATE_ORDON': 'datetime',
               'ORD_DATE_ORDER': 'datetime'},
    'MODSTOCK': {'MOD_DATE': 'datetime'},
}


class MediCoreCDC:
    """Consumer CDC Kafka -> Snowflake RAW pour les 4 tables CDC Debezium."""

    def __init__(self) -> None:
        self.kafka_servers: str = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
        self.sf_conn: snowflake.connector.SnowflakeConnection = self._get_snowflake_conn()
        self.sf_cursor = self.sf_conn.cursor()
        # Connexion DLQ dediee pour eviter qu'une erreur main ne coupe l'ecriture DLQ
        self.dlq_conn: snowflake.connector.SnowflakeConnection = self._get_snowflake_conn()
        self.dlq_cursor = self.dlq_conn.cursor()
        self._ensure_dlq()

    def _get_snowflake_conn(self) -> snowflake.connector.SnowflakeConnection:
        """Connexion Snowflake vers le schema RAW."""
        return snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            role=os.getenv('SNOWFLAKE_ROLE_NAME', 'MEDICORE_RAW_WRITER'),
            database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
            schema='RAW'
        )

    def _is_session_expired(self, err: Exception) -> bool:
        """Detecte une erreur de session Snowflake expiree (token, auth).

        Args:
            err: Exception Snowflake.

        Returns:
            True si l'erreur necessite une reconnexion.
        """
        errno = getattr(err, 'errno', None)
        return errno in SNOWFLAKE_AUTH_EXPIRED_CODES

    def _reconnect_main(self) -> None:
        """Recree la connexion Snowflake principale apres session expiree."""
        logger.warning("[SF] Session main expiree, reconnexion...")
        try:
            self.sf_cursor.close()
        except Exception:  # pylint: disable=broad-except
            pass
        try:
            self.sf_conn.close()
        except Exception:  # pylint: disable=broad-except
            pass
        self.sf_conn = self._get_snowflake_conn()
        self.sf_cursor = self.sf_conn.cursor()
        logger.info("[SF] Reconnexion main OK")

    def _reconnect_dlq(self) -> None:
        """Recree la connexion Snowflake DLQ apres session expiree."""
        logger.warning("[SF] Session DLQ expiree, reconnexion...")
        try:
            self.dlq_cursor.close()
        except Exception:  # pylint: disable=broad-except
            pass
        try:
            self.dlq_conn.close()
        except Exception:  # pylint: disable=broad-except
            pass
        self.dlq_conn = self._get_snowflake_conn()
        self.dlq_cursor = self.dlq_conn.cursor()
        logger.info("[SF] Reconnexion DLQ OK")

    def _ensure_dlq(self) -> None:
        """Cree la table _DLQ si elle n'existe pas."""
        self.sf_cursor.execute("""
            CREATE TABLE IF NOT EXISTS _DLQ (
                DLQ_ID NUMBER AUTOINCREMENT,
                SOURCE VARCHAR(20) NOT NULL,
                TABLE_NAME VARCHAR(50) NOT NULL,
                TOPIC VARCHAR(100),
                PAYLOAD VARCHAR,
                ERROR_MESSAGE VARCHAR,
                CREATED_AT TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
            )
        """)

    def _write_dlq(self, source: str, table_name: str, topic: Optional[str], payload: Any, error_msg: Any) -> None:
        """Ecrit un message/row invalide dans la dead-letter queue.

        Utilise une connexion dediee (self.dlq_conn) pour eviter qu'une session main
        expiree ne coupe l'ecriture DLQ. Reconnecte automatiquement si DLQ expire aussi.

        Args:
            source: Origine de l'erreur (cdc_parse, cdc_insert).
            table_name: Table Snowflake concernee.
            topic: Topic Kafka source.
            payload: Contenu du message en erreur.
            error_msg: Message d'erreur associe.
        """
        payload_json = json.dumps(payload, default=str)
        dlq_sql = (
            "INSERT INTO _DLQ (SOURCE, TABLE_NAME, TOPIC, PAYLOAD, ERROR_MESSAGE) "
            "VALUES (%s, %s, %s, %s, %s)"
        )
        dlq_values = (source, table_name, topic, payload_json, str(error_msg)[:4000])
        for attempt in (1, 2):
            try:
                self.dlq_cursor.execute(dlq_sql, dlq_values)
                return
            except snowflake.connector.errors.Error as dlq_err:
                if attempt == 1 and self._is_session_expired(dlq_err):
                    self._reconnect_dlq()
                    continue
                logger.warning(f"DLQ write failed: {dlq_err}")
                return

    def consume_cdc_batch(self) -> int:
        """Consomme les topics Kafka winstat.winstat.* vers RAW_* Snowflake.

        Accumule les events en micro-batch (BATCH_SIZE) avant flush.

        Returns:
            Nombre total d'events inseres.
        """
        topics = [f"{CDC_KAFKA_TOPIC_PREFIX}.{t}" for t in CDC_TABLES_KAFKA]
        consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=self.kafka_servers,
            group_id=CDC_KAFKA_GROUP_ID,
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')) if x else None,
            consumer_timeout_ms=BATCH_TIMEOUT_SEC * 1000,
        )

        # Buffers par table : { "RAW_COMMANDES": [event1, event2, ...], ... }
        buffers: Dict[str, List[Dict]] = {}
        processed = 0
        errors = 0
        had_flush_errors = False

        for message in consumer:
            topic = message.topic
            table_short = topic.split('.')[-1]
            table_name = f'RAW_{table_short.upper()}'

            # Skip tombstone messages (null value)
            if message.value is None:
                continue

            try:
                payload = message.value
                event = self._parse_debezium_event(payload)

                if table_name not in buffers:
                    buffers[table_name] = []
                buffers[table_name].append(event)

                # Flush si le buffer de cette table atteint BATCH_SIZE
                if len(buffers[table_name]) >= BATCH_SIZE:
                    flush_ok = self._flush_batch(table_name, buffers[table_name])
                    processed += len(buffers[table_name])
                    buffers[table_name] = []
                    # Ne commit que si flush reussi (evite la perte de donnees Kafka)
                    if flush_ok:
                        consumer.commit()
                    else:
                        had_flush_errors = True

            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                errors += 1
                logger.error(f"ERROR {topic}: {e}")
                self._write_dlq('cdc_parse', table_name, topic, message.value, e)
                continue

        # Flush les buffers restants (timeout Kafka atteint, plus de messages)
        final_flush_ok = True
        for table_name, events in buffers.items():
            if events:
                if not self._flush_batch(table_name, events):
                    final_flush_ok = False
                    had_flush_errors = True
                processed += len(events)

        # Commit final uniquement si le dernier flush a reussi
        if final_flush_ok:
            consumer.commit()
        logger.info(f"Batch termine: {processed} events inseres, {errors} erreurs parse"
                    + (" [flush errors - offsets partiels]" if had_flush_errors else ""))
        consumer.close()
        return processed

    def _decode_debezium_decimal(self, value: Any, scale: int) -> Optional[float]:
        """Decode un DECIMAL Debezium encode en base64 (BYTES logical type).

        Args:
            value: Valeur base64 a decoder.
            scale: Nombre de decimales du type DECIMAL source.

        Returns:
            Valeur float decodee, ou None si valeur nulle.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            return value

        try:
            decoded = base64.b64decode(value)
            int_val = int.from_bytes(decoded, byteorder="big", signed=True)
            decimal_val = Decimal(int_val) / Decimal(10 ** scale)
            return float(decimal_val)
        except (ValueError, TypeError) as exc:
            logger.warning(f"[DECIMAL] base64 non decodable: {value} ({exc})")
            return value

    def _parse_debezium_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Parse un event Debezium vers le format RAW avec metadata CDC.

        Args:
            payload: Event Debezium brut (avec cle 'payload').

        Returns:
            Dict contenant les donnees + metadata CDC.

        Raises:
            ValueError: Si le payload est invalide ou l'operation inconnue.
        """
        if 'payload' not in payload:
            raise ValueError(f"No 'payload' in event: {list(payload.keys())}")

        debezium_payload = payload['payload']
        op = debezium_payload['op']
        ts_ms = debezium_payload['ts_ms']

        # Extract data selon operation
        if op == 'c':  # CREATE
            data = debezium_payload['after']
            cdc_op = 'I'
        elif op == 'u':  # UPDATE
            data = debezium_payload['after']
            cdc_op = 'U'
        elif op == 'd':  # DELETE
            data = debezium_payload['before']
            cdc_op = 'D'
        elif op == 'r':  # READ (snapshot initial Debezium)
            data = debezium_payload['after']
            cdc_op = 'S'  # Snapshot
        else:
            raise ValueError(f"Unknown op: {op}")

        source_table = debezium_payload['source']['table']

        # Normalisation DATE / DATETIME : Debezium envoie des int (jours ou ms)
        # Snowflake attend DATE ou TIMESTAMP_NTZ -> convertir en datetime
        base_epoch = datetime(1970, 1, 1)
        for col, kind in CDC_DATE_COLUMNS.get(source_table, {}).items():
            val = data.get(col)
            if val is None or not isinstance(val, int):
                continue
            if kind == 'date':
                data[col] = (base_epoch + timedelta(days=val)).strftime("%Y-%m-%d")
            elif kind == 'datetime':
                data[col] = datetime.fromtimestamp(val / 1000)

        # Normalisation DECIMAL base64 (Debezium BYTES logical type)
        for col, scale in CDC_DECIMAL_COLUMNS.get(source_table, {}).items():
            if col in data:
                data[col] = self._decode_debezium_decimal(data[col], scale=scale)

        # Ajout metadata CDC (3 colonnes presentes dans RAW_* tables)
        # cdc_schema/cdc_table supprimes car absents du schema Snowflake (derivables
        # depuis le nom de la table cible)
        event = {
            **data,
            'cdc_operation': cdc_op,
            'cdc_timestamp': datetime.fromtimestamp(ts_ms / 1000),
            'cdc_lsn': debezium_payload['source']['pos']
        }

        return event

    def _flush_batch(self, table_name: str, events: List[Dict[str, Any]]) -> bool:
        """INSERT micro-batch via executemany(), fallback row-by-row en cas d'erreur.

        Comportement defensif :
        - Reconnecte si la session Snowflake a expire (code 390114) et retente une fois
        - Circuit-breaker : arrete le fallback row-by-row apres N echecs consecutifs
          (evite la boucle infinie sur erreur systemique type mismatch schema)
        - Retourne False si la phase a eu des erreurs -> l'appelant ne doit PAS
          commiter l'offset Kafka (evite la perte de donnees)

        Args:
            table_name: Table Snowflake cible (ex: RAW_COMMANDES).
            events: Liste d'events a inserer.

        Returns:
            True si tous les events ont ete inseres avec succes, False sinon.
        """
        if not events:
            return True

        # Colonnes depuis le premier event (tous les events d'une table ont les memes cles)
        columns = ", ".join(f'"{k.upper()}"' for k in events[0].keys())
        placeholders = ", ".join(["%s" for _ in events[0]])
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        values_list = [tuple(e.values()) for e in events]

        # Tentative batch avec retry sur session expiree (1 reconnexion max)
        for attempt in (1, 2):
            try:
                self.sf_cursor.executemany(query, values_list)
                logger.info(f"INSERT {table_name}: {len(events)} rows (batch)")
                return True
            except snowflake.connector.errors.Error as e:
                if attempt == 1 and self._is_session_expired(e):
                    self._reconnect_main()
                    continue
                logger.error(f"BATCH INSERT {table_name} failed ({len(events)} rows): {e}")
                break

        # Fallback row-by-row avec circuit-breaker
        # Si N rows consecutifs echouent avec la meme erreur racine -> systemique, abandonner
        inserted = 0
        consecutive_fails = 0
        last_err_signature: Optional[str] = None
        aborted = False

        for i, vals in enumerate(values_list):
            try:
                self.sf_cursor.execute(query, vals)
                inserted += 1
                consecutive_fails = 0
                last_err_signature = None
            except snowflake.connector.errors.Error as row_err:
                # Retry une fois apres reconnexion si session expiree
                if self._is_session_expired(row_err):
                    self._reconnect_main()
                    try:
                        self.sf_cursor.execute(query, vals)
                        inserted += 1
                        consecutive_fails = 0
                        last_err_signature = None
                        continue
                    except snowflake.connector.errors.Error as retry_err:
                        row_err = retry_err

                logger.error(f"  Row {i} failed: {row_err}")
                self._write_dlq('cdc_insert', table_name, None, events[i], row_err)

                # Circuit-breaker : erreur systemique (meme errno repete)
                # On utilise uniquement errno (stable) car le message contient un
                # request ID unique par appel qui rendrait chaque signature differente
                err_signature = str(getattr(row_err, 'errno', None) or type(row_err).__name__)
                if err_signature == last_err_signature:
                    consecutive_fails += 1
                else:
                    consecutive_fails = 1
                    last_err_signature = err_signature

                if consecutive_fails >= FALLBACK_MAX_CONSECUTIVE_FAILS:
                    remaining = len(values_list) - i - 1
                    logger.error(
                        f"  CIRCUIT-BREAKER {table_name}: {consecutive_fails} echecs "
                        f"consecutifs avec meme erreur ({err_signature}). "
                        f"Arret du fallback ({remaining} rows non traites)."
                    )
                    aborted = True
                    break

        logger.info(f"  Fallback: {inserted}/{len(events)} rows inserted"
                    + (" (ABORTED circuit-breaker)" if aborted else ""))
        return False

    def close(self) -> None:
        """Ferme proprement les curseurs et connexions Snowflake (main + DLQ)."""
        for c in (self.sf_cursor, self.dlq_cursor):
            try:
                c.close()
            except Exception:  # pylint: disable=broad-except
                pass
        for conn in (self.sf_conn, self.dlq_conn):
            try:
                conn.close()
            except Exception:  # pylint: disable=broad-except
                pass


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Consumer CDC Kafka -> Snowflake RAW')
    parser.add_argument('--run-id', default=None, help='Pipeline run ID pour audit')
    args = parser.parse_args()

    cdc = MediCoreCDC()
    try:
        processed = cdc.consume_cdc_batch()
        with open('/tmp/cdc_last_count', 'w') as f:
            f.write(str(processed))

        # Mesure du lag Kafka (end_offset - committed) par topic
        from utils.kafka_lag import get_consumer_lag, write_lag_metrics, log_lag_to_audit
        topics = [f"{CDC_KAFKA_TOPIC_PREFIX}.{t}" for t in CDC_TABLES_KAFKA]
        lag = get_consumer_lag(cdc.kafka_servers, CDC_KAFKA_GROUP_ID, topics)
        if lag:
            write_lag_metrics(lag)
            if args.run_id:
                log_lag_to_audit(args.run_id, lag)
    finally:
        cdc.close()
