#!/usr/bin/env python3
"""
Debezium se connecte à MySQL et publie les évènements binlog sur Kafka (topics)
Lit les événements Debezium sur Kafka + traite les nouveautés + écrit RAW_* avec métadonnées CDC dans Snowflake
daily_cdc_batch est appelé par batch_loop.sh

PII masking : non appliqué ici (RAW = données brutes).
Le masquage est effectué dans les modèles dbt STAGING (stg_orders, stg_pharmacie, etc.)
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
import snowflake.connector
from kafka import KafkaConsumer
import logging
import base64
from decimal import Decimal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Micro-batch : accumule N events ou attend TIMEOUT avant flush
BATCH_SIZE = 500
BATCH_TIMEOUT_SEC = int(os.getenv('CDC_BATCH_TIMEOUT_SEC', '30'))

class MediCoreCDC:
    def __init__(self):
        self.kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
        self.sf_conn = self._get_snowflake_conn()
        self.sf_cursor = self.sf_conn.cursor()

    def _get_snowflake_conn(self):
        """Connexion Snowflake RAW"""
        return snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            role='MEDIcore_DBT_EXECUTOR',
            database='MEDIcore',
            warehouse='MEDIcore_WH',
            schema='RAW'
        )

    def consume_cdc_batch(self):
        """Consomme les topics Kafka winstat_rds.winstat.* → RAW_* Snowflake (micro-batch)"""
        consumer = KafkaConsumer(
            *[
                'winstat_rds.winstat.COMMANDES',
                'winstat_rds.winstat.FACTURES',
                'winstat_rds.winstat.ORDERS',
                'winstat_rds.winstat.MODSTOCK',
            ],
            bootstrap_servers=self.kafka_servers,
            group_id='medi_core_cdc_batch_dev2',
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
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

            except Exception as e:
                errors += 1
                logger.error(f"ERROR {topic}: {e}")
                continue

        # Flush les buffers restants (timeout Kafka atteint, plus de messages)
        for table_name, events in buffers.items():
            if events:
                self._flush_batch(table_name, events)
                processed += len(events)

        logger.info(f"Batch termine: {processed} events inseres, {errors} erreurs")
        consumer.close()
    
    def _decode_debezium_decimal(self, value, scale: int):
        """Decode un DECIMAL Debezium encodé en base64 (BYTES logical type)."""
        if value is None:
            return None
        if not isinstance(value, str):
            return value

        try:
            decoded = base64.b64decode(value)
            int_val = int.from_bytes(decoded, byteorder="big", signed=True)
            decimal_val = Decimal(int_val) / Decimal(10 ** scale)
            return float(decimal_val)
        except Exception:
            logger.warning(f"⚠️ DECIMAL base64 non décodable: {value}")
            return value
        
    def _parse_debezium_event(self, payload: Dict) -> Dict:
        """Parse Debezium → format RAW avec CDC metadata"""
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
    
	
    def _flush_batch(self, table_name: str, events: List[Dict]):
        """INSERT micro-batch via executemany() — 10-50x plus rapide que row-by-row."""
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
        except Exception as e:
            logger.error(f"BATCH INSERT {table_name} failed ({len(events)} rows): {e}")
            # Fallback row-by-row pour identifier l'event problematique
            inserted = 0
            for i, vals in enumerate(values_list):
                try:
                    self.sf_cursor.execute(query, vals)
                    inserted += 1
                except Exception as row_err:
                    logger.error(f"  Row {i} failed: {row_err}")
            logger.info(f"  Fallback: {inserted}/{len(events)} rows inserted")

    def close(self):
        """Ferme proprement le curseur et la connexion Snowflake."""
        self.sf_cursor.close()
        self.sf_conn.close()


if __name__ == "__main__":
    cdc = MediCoreCDC()
    try:
        cdc.consume_cdc_batch()
    finally:
        cdc.close()
