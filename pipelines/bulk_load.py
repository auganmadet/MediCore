#!/usr/bin/env python3
"""
Bulk load MySQL RDS → Snowflake RAW (18 tables)
Approche : fichiers Parquet locaux → PUT @BULK_STAGE → COPY INTO (1 par table)

Usage:
  python bulk_load.py                          # 18 tables
  python bulk_load.py --tables PHARMACIE       # 1 table
  python bulk_load.py --cdc-only --truncate    # 4 tables CDC + truncate
  python bulk_load.py --ref-only               # 14 tables référence
  python bulk_load.py --chunk-size 500000      # chunks de 500K lignes
"""

import argparse
import os
import sys
import time
from datetime import datetime
import logging

import pandas as pd
import mysql.connector
import snowflake.connector

from utils.pii_masking import mask_pii

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Répertoire temporaire pour les fichiers Parquet
EXPORT_DIR = '/tmp/bulk_export'

# Stage Snowflake interne
STAGE_NAME = 'MEDICORE.RAW.BULK_STAGE'

# Mapping MySQL table (winstat) → Snowflake RAW table
TABLE_MAPPING = {
    # CDC tables (4)
    'COMMANDES':          'RAW_COMMANDES',
    'FACTURES':           'RAW_FACTURES',
    'ORDERS':             'RAW_ORDERS',
    'MODSTOCK':           'RAW_MODSTOCK',
    # Reference tables (14)
    'DAYBYDAY':           'RAW_DAYBYDAY',
    'EAN13':              'RAW_EAN13',
    'FOURNISSEURS':       'RAW_FOURNISSEURS',
    'HISTORY':            'RAW_HISTORY',
    'LOG':                'RAW_LOG',
    'LPPR':               'RAW_LPPR',
    'MANQHISTORY':        'RAW_MANQHISTORY',
    'MEDIPRIX_FACTURES':  'RAW_MEDIPRIX_FACTURES',
    'PHARMACIE':          'RAW_PHARMACIE',
    'PRODUITS':           'RAW_PRODUITS',
    'PRODUITS_NEGATIFS':  'RAW_PRODUITS_NEGATIFS',
    'STOCKHISTORY':       'RAW_STOCKHISTORY',
    'pharmacies':         'RAW_PHARMACIES',
    'pharmacies_erreur':  'RAW_PHARMACIES_ERREUR',
}

CDC_TABLES = ['COMMANDES', 'FACTURES', 'ORDERS', 'MODSTOCK']
REF_TABLES = [t for t in TABLE_MAPPING if t not in CDC_TABLES]


def get_mysql_conn():
    """Connexion MySQL RDS"""
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE', 'winstat')
    )


def get_snowflake_conn():
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


def get_snowflake_columns(sf_conn, table_name):
    """Récupère les noms de colonnes Snowflake (casing exact)."""
    cursor = sf_conn.cursor()
    cursor.execute(f"DESCRIBE TABLE {table_name}")
    columns = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return columns


def ensure_stage(sf_conn):
    """Crée le stage interne s'il n'existe pas."""
    cursor = sf_conn.cursor()
    cursor.execute(f"CREATE STAGE IF NOT EXISTS {STAGE_NAME}")
    cursor.close()
    logger.info(f"Stage {STAGE_NAME} prêt")


def ensure_export_dir():
    """Crée le répertoire temporaire pour les fichiers Parquet."""
    os.makedirs(EXPORT_DIR, exist_ok=True)


def bulk_load_table(mysql_conn, sf_conn, mysql_table, sf_table, chunk_size, truncate):
    """
    Charge une table MySQL → Snowflake RAW via Parquet + stage + COPY INTO.

    Flux :
      MySQL → chunks de N lignes → PII masking → Parquet local → PUT @stage
      → 1 seul COPY INTO (Snowflake parallélise sur tous les fichiers)
      → REMOVE @stage/<table>/
    """
    logger.info(f"{'='*60}")
    logger.info(f"Loading {mysql_table} -> {sf_table}...")
    start = time.time()

    if truncate:
        sf_conn.cursor().execute(f"TRUNCATE TABLE {sf_table}")
        logger.info(f"  TRUNCATE {sf_table}")

    # Colonnes Snowflake (casing exact)
    sf_columns = get_snowflake_columns(sf_conn, sf_table)
    sf_col_upper_map = {c.upper(): c for c in sf_columns}
    sf_col_set = set(sf_columns)

    # Colonnes CDC metadata
    cdc_cols = {'CDC_OPERATION', 'CDC_TIMESTAMP', 'CDC_SCHEMA', 'CDC_TABLE', 'CDC_LSN'}

    # Nettoyer le sous-dossier stage pour cette table
    stage_path = f"@{STAGE_NAME}/{sf_table}/"
    sf_conn.cursor().execute(f"REMOVE {stage_path}")

    # Lecture MySQL par chunks → fichiers Parquet → PUT
    query = f"SELECT * FROM `{mysql_table}`"
    total_rows = 0
    chunk_num = 0

    for chunk_df in pd.read_sql(query, mysql_conn, chunksize=chunk_size):
        chunk_num += 1
        chunk_start = time.time()

        # PII masking ligne par ligne
        masked_rows = []
        for _, row in chunk_df.iterrows():
            row_dict = row.to_dict()
            masked = mask_pii(row_dict, sf_table)
            masked_rows.append(masked)

        df = pd.DataFrame(masked_rows)

        # Renommer colonnes MySQL → casing Snowflake
        df.columns = [sf_col_upper_map.get(c.upper(), c.upper()) for c in df.columns]

        # Ajouter métadonnées CDC
        now = datetime.now()
        cdc_metadata = {
            'CDC_OPERATION': 'S',
            'CDC_TIMESTAMP': now,
            'CDC_SCHEMA': 'winstat',
            'CDC_TABLE': mysql_table,
            'CDC_LSN': None,
        }
        for col_upper, value in cdc_metadata.items():
            sf_col_name = sf_col_upper_map.get(col_upper)
            if sf_col_name and sf_col_name in sf_col_set:
                df[sf_col_name] = value

        # Ne garder que les colonnes existantes dans Snowflake
        valid_cols = [c for c in df.columns if c in sf_col_set]
        df = df[valid_cols]

        # Écrire fichier Parquet local
        parquet_file = os.path.join(EXPORT_DIR, f"{sf_table}_{chunk_num:04d}.parquet")
        df.to_parquet(parquet_file, engine='pyarrow', index=False)
        file_size_mb = os.path.getsize(parquet_file) / (1024 * 1024)

        # PUT vers stage Snowflake
        put_query = f"PUT 'file://{parquet_file}' {stage_path} AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        sf_conn.cursor().execute(put_query)

        # Supprimer fichier local (nettoyage progressif)
        os.remove(parquet_file)

        total_rows += len(df)
        chunk_time = time.time() - chunk_start
        logger.info(f"  Chunk {chunk_num}: {len(df)} rows, {file_size_mb:.1f} Mo, PUT {chunk_time:.1f}s | Total: {total_rows}")

    if total_rows == 0:
        logger.warning(f"  {sf_table}: table vide (0 rows)")
        return 0

    # COPY INTO : 1 seule opération pour tous les fichiers Parquet du stage
    logger.info(f"  COPY INTO {sf_table} depuis {stage_path} ({chunk_num} fichiers)...")
    copy_start = time.time()
    cursor = sf_conn.cursor()
    cursor.execute(f"""
        COPY INTO {sf_table}
        FROM {stage_path}
        FILE_FORMAT = (TYPE = PARQUET)
        MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
    """)
    copy_time = time.time() - copy_start
    logger.info(f"  COPY INTO terminé en {copy_time:.1f}s")

    # Nettoyer le stage
    sf_conn.cursor().execute(f"REMOVE {stage_path}")

    elapsed = time.time() - start
    logger.info(f"  {sf_table}: {total_rows} rows en {elapsed:.1f}s ({chunk_num} fichiers Parquet)")
    return total_rows


def main():
    parser = argparse.ArgumentParser(description='Bulk load MySQL RDS -> Snowflake RAW (18 tables) via Parquet + stage')
    parser.add_argument('--tables', nargs='+', help='Tables specifiques (ex: PHARMACIE PRODUITS)')
    parser.add_argument('--cdc-only', action='store_true', help='4 tables CDC uniquement')
    parser.add_argument('--ref-only', action='store_true', help='14 tables reference uniquement')
    parser.add_argument('--chunk-size', type=int, default=1000000, help='Lignes par fichier Parquet (defaut: 1000000)')
    parser.add_argument('--truncate', action='store_true', help='TRUNCATE TABLE avant insertion')
    args = parser.parse_args()

    # Déterminer les tables à charger
    if args.tables:
        tables = {}
        for t in args.tables:
            if t in TABLE_MAPPING:
                tables[t] = TABLE_MAPPING[t]
            else:
                logger.warning(f"Table inconnue ignoree: {t}")
    elif args.cdc_only:
        tables = {t: TABLE_MAPPING[t] for t in CDC_TABLES}
    elif args.ref_only:
        tables = {t: TABLE_MAPPING[t] for t in REF_TABLES}
    else:
        tables = TABLE_MAPPING.copy()

    if not tables:
        logger.error("Aucune table a charger")
        sys.exit(1)

    logger.info(f"{'='*60}")
    logger.info(f"Bulk load: {len(tables)} tables, chunk_size={args.chunk_size:,}, truncate={args.truncate}")
    logger.info(f"Methode: Parquet + PUT @{STAGE_NAME} + COPY INTO")
    logger.info(f"{'='*60}")

    # Connexion Snowflake + préparation
    sf_conn = get_snowflake_conn()
    ensure_stage(sf_conn)
    ensure_export_dir()

    grand_total = 0
    errors = []
    results = []
    start_all = time.time()

    for mysql_table, sf_table in tables.items():
        # Nouvelle connexion MySQL par table (évite "Unread result found")
        mysql_conn = get_mysql_conn()
        try:
            rows = bulk_load_table(mysql_conn, sf_conn, mysql_table, sf_table, args.chunk_size, args.truncate)
            grand_total += rows
            results.append((sf_table, rows))
        except Exception as e:
            logger.error(f"ERREUR {mysql_table}: {e}")
            errors.append(mysql_table)
        finally:
            mysql_conn.close()

    elapsed_all = time.time() - start_all

    # Résumé final
    logger.info(f"{'='*60}")
    logger.info(f"RÉSUMÉ BULK LOAD")
    logger.info(f"{'='*60}")
    for sf_table, rows in results:
        logger.info(f"  {sf_table:30s} : {rows:>12,} rows")
    logger.info(f"{'='*60}")
    logger.info(f"  TOTAL : {grand_total:>12,} rows en {elapsed_all:.1f}s")

    if errors:
        logger.warning(f"Tables en erreur: {errors}")
        sys.exit(1)

    sf_conn.close()
    logger.info("Bulk load termine avec succes")


if __name__ == '__main__':
    main()
