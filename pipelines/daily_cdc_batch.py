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


class MediCoreCDC:
    """Consumer CDC Kafka -> Snowflake RAW pour les 4 tables CDC Debezium."""

    def __init__(self) -> None:
        self.kafka_servers: str = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
        self.sf_conn: snowflake.connector.SnowflakeConnection = self._get_snowflake_conn()
        self.sf_cursor = self.sf_conn.cursor()
        self._ensure_dlq()

    def _get_snowflake_conn(self) -> snowflake.connector.SnowflakeConnection:
        """Connexion Snowflake vers le schema RAW."""
        return snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            role=os.getenv('SNOWFLAKE_ROLE_NAME', 'MEDICORE_RAW_WRITER'),
            database=os.getenv('SNOWFLAKE_DATABASE', 'MEDIcore'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDIcore_WH'),
            schema='RAW'
        )

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

        Args:
            source: Origine de l'erreur (cdc_parse, cdc_insert).
            table_name: Table Snowflake concernee.
            topic: Topic Kafka source.
            payload: Contenu du message en erreur.
            error_msg: Message d'erreur associe.
        """
        try:
            payload_json = json.dumps(payload, default=str)
            self.sf_cursor.execute(
                "INSERT INTO _DLQ (SOURCE, TABLE_NAME, TOPIC, PAYLOAD, ERROR_MESSAGE) "
                "VALUES (%s, %s, %s, %s, %s)",
                (source, table_name, topic, payload_json, str(error_msg)[:4000])
            )
        except snowflake.connector.errors.ProgrammingError as dlq_err:
            logger.warning(f"DLQ write failed: {dlq_err}")

    def consume_cdc_batch(self) -> int:
        """Consomme les topics Kafka winstat_rds.winstat.* vers RAW_* Snowflake.

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
                    self._flush_batch(table_name, buffers[table_name])
                    processed += len(buffers[table_name])
                    buffers[table_name] = []
                    consumer.commit()

            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                errors += 1
                logger.error(f"ERROR {topic}: {e}")
                self._write_dlq('cdc_parse', table_name, topic, message.value, e)
                continue

        # Flush les buffers restants (timeout Kafka atteint, plus de messages)
        for table_name, events in buffers.items():
            if events:
                self._flush_batch(table_name, events)
                processed += len(events)

        consumer.commit()
        logger.info(f"Batch termine: {processed} events inseres, {errors} erreurs")
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

        # Normalisation de COM_DATE (Debezium l'envoie en nombre de jours depuis 1970-01-01)
        raw_date = data.get("COM_DATE")
        if raw_date is not None:
            if isinstance(raw_date, int):
                base = datetime(1970, 1, 1)
                dt = base + timedelta(days=raw_date)
                data["COM_DATE"] = dt.strftime("%Y-%m-%d")
            elif isinstance(raw_date, str):
                data["COM_DATE"] = raw_date

        # Normalisation DECIMAL base64 (Debezium BYTES logical type)
        data["COM_PAHTNET"] = self._decode_debezium_decimal(data.get("COM_PAHTNET"), scale=2)
        data["COM_TAUXREMISE"] = self._decode_debezium_decimal(data.get("COM_TAUXREMISE"), scale=2)

        # Ajout metadata CDC
        event = {
            **data,
            'cdc_operation': cdc_op,
            'cdc_timestamp': datetime.fromtimestamp(ts_ms / 1000),
            'cdc_schema': debezium_payload['source']['db'],
            'cdc_table': debezium_payload['source']['table'],
            'cdc_lsn': debezium_payload['source']['pos']
        }

        return event

    def _flush_batch(self, table_name: str, events: List[Dict[str, Any]]) -> None:
        """INSERT micro-batch via executemany(), fallback row-by-row en cas d'erreur.

        Args:
            table_name: Table Snowflake cible (ex: RAW_COMMANDES).
            events: Liste d'events a inserer.
        """
        if not events:
            return

        # Colonnes depuis le premier event (tous les events d'une table ont les memes cles)
        columns = ", ".join(f'"{k.upper()}"' for k in events[0].keys())
        placeholders = ", ".join(["%s" for _ in events[0]])
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        # Transformer les events en liste de tuples
        values_list = [tuple(e.values()) for e in events]

        try:
            self.sf_cursor.executemany(query, values_list)
            logger.info(f"INSERT {table_name}: {len(events)} rows (batch)")
        except snowflake.connector.errors.Error as e:
            logger.error(f"BATCH INSERT {table_name} failed ({len(events)} rows): {e}")
            # Fallback row-by-row pour identifier l'event problematique
            inserted = 0
            for i, vals in enumerate(values_list):
                try:
                    self.sf_cursor.execute(query, vals)
                    inserted += 1
                except snowflake.connector.errors.Error as row_err:
                    logger.error(f"  Row {i} failed: {row_err}")
                    self._write_dlq('cdc_insert', table_name, None, events[i], row_err)
            logger.info(f"  Fallback: {inserted}/{len(events)} rows inserted")

    def close(self) -> None:
        """Ferme proprement le curseur et la connexion Snowflake."""
        self.sf_cursor.close()
        self.sf_conn.close()


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
    finally:
        cdc.close()
