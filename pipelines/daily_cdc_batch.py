#!/usr/bin/env python3
"""
Debezium se connecte à MySQL et publie les évènements binlog sur Kafka (topics)
Lit les événements Debezium sur Kafka + traite les nouveautés + écrit RAW_* avec métadonnées CDC dans Snowflake
daily_cdc_batch est appelé par batch_loop.sh
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, Any
import snowflake.connector
from kafka import KafkaConsumer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MediCoreCDC:
    def __init__(self):
        self.kafka_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092')
        self.sf_conn = self._get_snowflake_conn()
        
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
        """Consomme les topics winstat.* → RAW_*"""
        consumer = KafkaConsumer(
            'winstat.*',  # Tous les topics MySQL
            bootstrap_servers=self.kafka_servers,
            group_id='medi_core_cdc_batch',
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        processed = 0
        for message in consumer:
            topic = message.topic.replace('winstat.', '').upper()
            table_name = f'RAW_{topic}'
            
            try:
                event = self._parse_debezium_event(message.value)
                self._insert_raw_event(table_name, event)
                processed += 1
                
                if processed % 100 == 0:
                    logger.info(f"✅ {processed} events → {table_name}")
                    
            except Exception as e:
                logger.error(f"❌ Error {top                              ic}: {e}")
                continue
        
        logger.info(f"🎉 Batch terminé: {processed} events")
        consumer.close()
    
    def _parse_debezium_event(self, payload: Dict) -> Dict:
        """Parse Debezium → format RAW avec CDC metadata"""
        op = payload['payload']['op']
        ts_ms = payload['payload']['ts_ms']
        
        if op == 'c':  # CREATE
            data = payload['payload']['after']
            cdc_op = 'I'
        elif op == 'u':  # UPDATE
            data = payload['payload']['after']
            cdc_op = 'U'
        elif op == 'd':  # DELETE
            data = payload['payload']['before']
            cdc_op = 'D'
        else:
            raise ValueError(f"Unknown op: {op}")
        
        return {
            **data,
            'cdc_operation': cdc_op,
            'cdc_timestamp': datetime.fromtimestamp(ts_ms / 1000),
            'cdc_schema': payload['payload']['source']['db'],
            'cdc_table': payload['payload']['source']['table'],
            'cdc_lsn': payload['payload']['source']['pos']
        }
    
    def _insert_raw_event(self, table_name: str, event: Dict):
        """INSERT événement dans RAW_{table_name}"""
        cursor = self.sf_conn.cursor()
        
        columns = ', '.join(event.keys())
        placeholders = ', '.join(['?' for _ in event])
        values = list(event.values())
        
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        cursor.execute(query, values)
        
        if cursor.rowcount > 0:
            logger.debug(f"INSERT {table_name}: {cursor.rowcount} rows")
        
        cursor.close()

if __name__ == "__main__":
    cdc = MediCoreCDC()
    cdc.consume_cdc_batch()
