#!/usr/bin/env python3
"""
Debezium se connecte à MySQL et publie les évènements binlog sur Kafka (topics)
Lit les événements Debezium sur Kafka + traite les nouveautés + écrit RAW_* avec métadonnées CDC dans Snowflake
daily_cdc_batch est appelé par batch_loop.sh
"""

import json
import os
import sys
import hashlib
from datetime import datetime
from typing import Dict, Any
import snowflake.connector
from kafka import KafkaConsumer
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
        """Consomme les topics Kafka winstat.* → RAW_* Snowflake"""
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
            
            logger.info(f"📨 Topic: {message.topic} → {table_name}")
            
            try:
                payload = message.value
                event = self._parse_debezium_event(payload)
                event = self._mask_pii(event, topic)          # 🛡️ PII MASQUAGE
                self._insert_raw_event(table_name, event)
                processed += 1
                
                logger.info(f"✅ {processed} events processed")
                if processed % 50 == 0:
                    logger.info(f"📊 {processed} total events → {table_name}")
                    
            except Exception as e:
                logger.error(f"❌ ERROR {topic}: {e}")
                logger.error(f"Payload sample: {json.dumps(message.value, indent=2)[:500]}...")
                continue
        
        logger.info(f"🎉 Batch terminé: {processed} events")
        consumer.close()
    
    def _parse_debezium_event(self, payload: Dict) -> Dict:
        """Parse Debezium → format RAW avec CDC metadata"""
        logger.info(f"🔍 DEBUG payload keys: {list(payload.keys())}")
        
        # Debezium structure: {"payload": {"op": "c", "after": {...}}}
        if 'payload' not in payload:
            raise ValueError(f"No 'payload' in event: {list(payload.keys())}")
        
        debezium_payload = payload['payload']
        op = debezium_payload['op']
        ts_ms = debezium_payload['ts_ms']
        
        logger.info(f"🔍 DEBUG: op={op}, ts_ms={ts_ms}")
        
        # Extract data selon operation
        if op == 'c':  # CREATE
            # data = debezium_payload.get('after', {})
            data = debezium_payload['after']
            cdc_op = 'I'
        elif op == 'u':  # UPDATE
            # data = debezium_payload.get('after', {})
            data = debezium_payload['after']
            cdc_op = 'U'
        elif op == 'd':  # DELETE
            # data = debezium_payload.get('before', {})
            data = debezium_payload['before']
            cdc_op = 'D'
        else:
            raise ValueError(f"Unknown op: {op}")
        
        logger.info(f"🔍 DEBUG data keys: {list(data.keys())}")
        logger.info(f"🔍 Sample data: {dict(list(data.items())[:3])}...")  # 3 premières colonnes
        
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
    
def _mask_pii(self, event: Dict, table_name: str) -> Dict:
    """🛡️ Masquage PII MediCore - RGPD compliant"""
    masked = event.copy()
    
    # RAW_ORDERS : Patients + Opérateur
    if 'ORDERS' in table_name.upper():
        # Opérateur pharmacie
        if 'ORD_OPERATEUR' in masked:
            masked['ORD_OPERATEUR'] = f"USER_{hashlib.md5(str(masked['ORD_OPERATEUR']).encode()).hexdigest()[:4].upper()}"
        
        # Âge patient → quartile anonyme
        if 'ORD_CLIENT_AGE_MONTHS' in masked and masked['ORD_CLIENT_AGE_MONTHS']:
            age_months = int(masked['ORD_CLIENT_AGE_MONTHS'])
            quartile = (age_months // 36) * 36  # Par tranche 3 ans
            masked['ORD_CLIENT_AGE_MONTHS'] = f"{quartile}-{quartile+35}m"
        
        # Département → masqué
        if 'ORD_CLIENT_DEPARTEMENT' in masked:
            masked['ORD_CLIENT_DEPARTEMENT'] = f"DEP{str(masked['ORD_CLIENT_DEPARTEMENT'])[:2]}***"
    
    # RAW_PHARMACIE : Nom officine
    if 'PHARMACIE' in table_name.upper():
        if 'PHA_NOM' in masked:
            masked['PHA_NOM'] = f"PHARM_{hashlib.md5(str(masked['PHA_NOM']).encode()).hexdigest()[:4].upper()}"
    
    # RAW_PHARMACIES : Coordonnées sensibles
    if 'PHARMACIES' in table_name.upper():
        # ADELI pharmacien
        if 'adeli' in masked:
            masked['adeli'] = f"***{masked['adeli'][-4:]}"
        # Nom officine
        if 'name' in masked:
            masked['name'] = f"PHARM_{hashlib.md5(str(masked['name']).encode()).hexdigest()[:4].upper()}"
        # Téléphone
        if 'phone' in masked:
            phone = str(masked['phone']).replace(' ', '').replace('.', '')
            masked['phone'] = f"{phone[:2]}**{phone[-4:]}"
        # Code postal
        if 'postal_code' in masked:
            masked['postal_code'] = f"{masked['postal_code'][:2]}***"
    
    # RAW_MEDIPRIX_FACTURES
    if 'MEDIPRIX_FACTURES' in table_name.upper():
        if 'ORD_OPERATEUR' in masked:
            masked['ORD_OPERATEUR'] = f"USER_{hashlib.md5(str(masked['ORD_OPERATEUR']).encode()).hexdigest()[:4].upper()}"
        if 'PHA_NOM' in masked:
            masked['PHA_NOM'] = f"PHARM_{hashlib.md5(str(masked['PHA_NOM']).encode()).hexdigest()[:4].upper()}"
    
    # Fournisseurs B2B = public → NON masqué
    if 'FOURNISSEURS' in table_name.upper():
        pass  # Garder tel quel
    
    return masked
    
    def _insert_raw_event(self, table_name: str, event: Dict):
        """INSERT évènement dans Snowflake RAW_{table_name}"""
        cursor = self.sf_conn.cursor()
        
        columns = ', '.join(f'"{k}"' for k in event.keys())
        placeholders = ', '.join(['?' for _ in event])
        values = list(event.values())
        
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        
        logger.debug(f"🔍 INSERT DEBUG:")
        logger.debug(f"  Table: {table_name}")
        logger.debug(f"  Columns: {columns[:100]}...")
        logger.debug(f"  Values count: {len(values)}")
        logger.debug(f"  Query preview: {query[:150]}...")
        
        cursor.execute(query, values)
        
        if cursor.rowcount > 0:
            logger.info(f"✅ INSERT {table_name}: {cursor.rowcount} rows")
        else:
            logger.warning(f"⚠️  No rows inserted {table_name}")
        
        cursor.close()

if __name__ == "__main__":
    cdc = MediCoreCDC()
    cdc.consume_cdc_batch()
