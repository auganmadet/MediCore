"""CDC Ingestion via MySQL binlog avec Debezium + masquage PII"""
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any
import mysql.connector
from kafka import KafkaConsumer
from utils.mysql_connector import MySQLConnector
from utils.snowflake_connector import SnowflakeConnector
from utils.pii_processor import PIIProcessor
from utils.audit_logger import AuditLogger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CDCIngestion:
    def __init__(self):
        self.mysql_conn = MySQLConnector()
        self.sf_conn = SnowflakeConnector()
        self.pii_processor = PIIProcessor()
        self.audit = AuditLogger()
        
    def consume_cdc_events(self, topic_prefix: str = "mysql.winstat"):
        """Consomme les événements CDC depuis Kafka/Debezium"""
        consumer = KafkaConsumer(
            f'{topic_prefix}.*',
            bootstrap_servers=os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        for message in consumer:
            table_name = message.topic.split('.')[-1].upper()
            event = message.value['payload']
            
            # Masquage PII selon config
            masked_event = self.pii_processor.mask_pii(event, table_name)
            
            # Écriture staging Snowflake RAW
            self.write_to_raw(masked_event, table_name)
            
            # Audit trail
            self.audit.log_cdc_event(table_name, event['op'], len(masked_event))
            
    def write_to_raw(self, event: Dict, table_name: str):
        """Écrit l'événement CDC masqué vers RAW Snowflake"""
        columns = ', '.join(event['before'].keys() if event['op'] == 'd' else event['after'].keys())
        placeholders = ', '.join(['?' for _ in event['before'].keys()])
        
        # Ajout métadonnées CDC
        cdc_data = {
            'cdc_operation': event['op'],  # c, u, d
            'cdc_timestamp': datetime.fromtimestamp(event['ts_ms'] / 1000),
            'cdc_lsn': event['source']['position']
        }
        
        values = list(event['after'].values()) + list(cdc_data.values()) if event['op'] != 'd' else list(event['before'].values()) + list(cdc_data.values())
        
        self.sf_conn.execute_insert(f"RAW_{table_name}", columns, values)

if __name__ == "__main__":
    cdc = CDCIngestion()
    cdc.consume_cdc_events()
