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
from datetime import datetime, timedelta
from typing import Dict, Any
import snowflake.connector
from kafka import KafkaConsumer
import logging
import base64
from decimal import Decimal

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
        """Consomme les topics Kafka winstat_rds.winstat.* → RAW_* Snowflake"""
        consumer = KafkaConsumer(
            *[
                'winstat_rds.winstat.COMMANDES',
                'winstat_rds.winstat.FACTURES',
                'winstat_rds.winstat.ORDERS',
                'winstat_rds.winstat.PHARMACIE',
                'winstat_rds.winstat.MODSTOCK',
                'winstat_rds.winstat.DAYBYDAY',
            ],
            bootstrap_servers=self.kafka_servers,
            # group_id='medi_core_cdc_batch',   # modifier group_id pour repartir propre
            group_id='medi_core_cdc_batch_dev2',
            # auto_offset_reset='earliest',   # consumer MediCoreCDC lit tout l’historique (setup initial) depuis le début (snapshot + CDC)
            auto_offset_reset='latest',       # consumer MediCoreCDC ne lit que les nouveaux (CDC)
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        processed = 0
        for message in consumer:
            # topic = message.topic.replace('winstat.', '').upper()
            # table_name = f'RAW_{topic}'
            topic = message.topic  # ex: winstat_rds.winstat.COMMANDES
            logical = topic.replace('winstat_rds.', '')     # Enlever le préfixe "winstat_rds." uniquement → "winstat.COMMANDES"
            table_short = logical.split('.')[-1]            # Récupérer le dernier de la liste → "COMMANDES"
            table_name = f'RAW_{table_short.upper()}'       # → RAW_COMMANDES
            
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
        
        logger.info(f"🔍 COM_DATE brut depuis Debezium: {data.get('COM_DATE')} ({type(data.get('COM_DATE'))})")

        # Normalisation de COM_DATE (Debezium l'envoie en NUMBER le nombre de jours depuis 1970-01-01)
        raw_date = data.get("COM_DATE")
        if raw_date is not None:
            # Debezium MySQL DATE → jours depuis 1970-01-01 (ex: 20491)
            if isinstance(raw_date, int):
                base = datetime(1970, 1, 1)
                dt = base + timedelta(days=raw_date)
                data["COM_DATE"] = dt.strftime("%Y-%m-%d")
            elif isinstance(raw_date, str):
                # fallback simple
                data["COM_DATE"] = raw_date

        # # Normalisation de COM_PAHTNET : Debezium encode certains DECIMAL/NUMERIC en base64 quand le connecteur n’a pas de représentation native.
        # raw_pahtnet = data.get("COM_PAHTNET")
        # if raw_pahtnet is not None:
        #     # Cas DECIMAL encodé en base64 (string courte, chars base64)
        #     if isinstance(raw_pahtnet, str):
        #         try:
        #             decoded = base64.b64decode(raw_pahtnet)
        #             # Ici, il faut interpréter les bytes comme un entier signé big-endian,
        #             # puis appliquer l'échelle du DECIMAL (2 décimales dans NUMBER(8,2))
        #             int_val = int.from_bytes(decoded, byteorder="big", signed=True)
        #             decimal_val = Decimal(int_val) / Decimal("100")  # scale=2 car COM_PAHTNET est NUMBER(8,2)
        #             data["COM_PAHTNET"] = float(decimal_val)
        #         except Exception:
        #             # Si ce n'est pas du base64, on laisse la valeur telle quelle
        #             logger.warning(f"⚠️ COM_PAHTNET non décodable base64: {raw_pahtnet}")
        #     # Si c'est déjà un nombre, RAF

        # # Normalisation de COM_TAUXREMISE : Debezium encode certains DECIMAL/NUMERIC en base64 quand le connecteur n’a pas de représentation native.    
        # raw_taux = data.get("COM_TAUXREMISE")
        # if raw_taux is not None:
        #     if isinstance(raw_taux, str):
        #         try:
        #             decoded = base64.b64decode(raw_taux)
        #             int_val = int.from_bytes(decoded, byteorder="big", signed=True)
        #             # COM_TAUXREMISE est NUMBER(6,2) → scale 2 aussi
        #             decimal_val = Decimal(int_val) / Decimal("100")
        #             data["COM_TAUXREMISE"] = float(decimal_val)
        #         except Exception:
        #             logger.warning(f"⚠️ COM_TAUXREMISE non décodable base64: {raw_taux}")
        #     # si c'est déjà un nombre, RAF

        # Normalisation de COM_PAHTNET : NUMBER(8,2)
        data["COM_PAHTNET"] = self._decode_debezium_decimal(data.get("COM_PAHTNET"), scale=2)
        
        # Normalisation de COM_TAUXREMISE : NUMBER(6,2)
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
            pass  
    
        return masked
    
		

    # def _insert_raw_event(self, table_name: str, event: Dict):
    #     """INSERT évènement dans Snowflake RAW_{table_name}"""
    #     cursor = self.sf_conn.cursor()
        
    #     columns = ', '.join(f'"{k}"' for k in event.keys())
    #     placeholders = ', '.join(['?' for _ in event])
    #     values = list(event.values())
        
    #     query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        
    #     # logger.debug -> logger.info (plus light pour la PROD)
    #     logger.info(f"🔍 INSERT DEBUG:")
    #     logger.info(f"  Table: {table_name}")
    #     logger.info(f"  Columns: {columns[:100]}...")
    #     logger.info(f"  Values count: {len(values)}")
    #     logger.info(f"  Query preview: {query[:150]}...")
        
    #     cursor.execute(query, values)
        
    #     if cursor.rowcount > 0:
    #         logger.info(f"✅ INSERT {table_name}: {cursor.rowcount} rows")
    #     else:
    #         logger.warning(f"⚠️  No rows inserted {table_name}")
        
    #     cursor.close()

    def _insert_raw_event(self, table_name: str, event: Dict):
        """INSERT évènement dans Snowflake RAW_*"""
        cursor = self.sf_conn.cursor()

        # Colonnes et valeurs
        # columns = ", ".join(f'"{k}"' for k in event.keys())
        columns = ", ".join(f'"{k.upper()}"' for k in event.keys())     # Par défaut, Snowflake stocke les identifiants non quotés en MAJUSCULE
        # On utilise le style 'format' avec %s pour chaque colonne
        placeholders = ", ".join(["%s" for _ in event])
        values = list(event.values())

        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        logger.info("🔍 INSERT DEBUG:")
        logger.info(f"  Table: {table_name}")
        logger.info(f"  Columns: {columns[:200]}...")
        logger.info(f"  Values count: {len(values)}")
        logger.info(f"  Query preview: {query[:200]}...")

        # Exécution paramétrée
        cursor.execute(query, values)

        if cursor.rowcount > 0:
            logger.info(f"✅ INSERT {table_name}: {cursor.rowcount} rows")
        else:
            logger.warning(f"⚠️ No rows inserted {table_name}")

        cursor.close()    

if __name__ == "__main__":
    cdc = MediCoreCDC()
    cdc.consume_cdc_batch()
