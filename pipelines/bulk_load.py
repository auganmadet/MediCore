#!/usr/bin/env python3
"""
Bulk load MySQL RDS → Snowflake RAW (18 tables) via write_pandas()
Usage:
  python bulk_load.py                          # 18 tables
  python bulk_load.py --tables PHARMACIE       # 1 table
  python bulk_load.py --cdc-only --truncate    # 4 tables CDC + truncate
  python bulk_load.py --ref-only               # 14 tables référence
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
from snowflake.connector.pandas_tools import write_pandas

from utils.pii_masking import mask_pii

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    """Connexion Snowflake RAW (pattern daily_cdc_batch.py)"""
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


def bulk_load_table(mysql_conn, sf_conn, mysql_table, sf_table, chunk_size, truncate):
    """Charge une table MySQL → Snowflake RAW via write_pandas()"""
    logger.info(f"Loading {mysql_table} -> {sf_table}...")
    start = time.time()

    if truncate:
        sf_conn.cursor().execute(f"TRUNCATE TABLE {sf_table}")
        logger.info(f"  TRUNCATE {sf_table}")

    # Colonnes Snowflake (casing exact pour write_pandas)
    sf_columns = get_snowflake_columns(sf_conn, sf_table)
    sf_col_upper_map = {c.upper(): c for c in sf_columns}
    sf_col_set = set(sf_columns)

    # Lecture MySQL par chunks
    query = f"SELECT * FROM `{mysql_table}`"
    total_rows = 0

    for chunk_df in pd.read_sql(query, mysql_conn, chunksize=chunk_size):
        # PII masking ligne par ligne
        masked_rows = []
        for _, row in chunk_df.iterrows():
            row_dict = row.to_dict()
            masked = mask_pii(row_dict, sf_table)
            masked_rows.append(masked)

        df = pd.DataFrame(masked_rows)

        # Renommer colonnes MySQL → casing Snowflake
        df.columns = [sf_col_upper_map.get(c.upper(), c.upper()) for c in df.columns]

        # Ajouter métadonnées CDC (seulement si la colonne existe dans Snowflake)
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

        # write_pandas : DataFrame → Parquet → PUT @stage → COPY INTO
        write_pandas(sf_conn, df, sf_table)
        total_rows += len(df)
        logger.info(f"  {sf_table}: {total_rows} rows loaded...")

    elapsed = time.time() - start
    logger.info(f"  {sf_table}: {total_rows} rows in {elapsed:.1f}s")
    return total_rows


def main():
    parser = argparse.ArgumentParser(description='Bulk load MySQL RDS -> Snowflake RAW (18 tables)')
    parser.add_argument('--tables', nargs='+', help='Tables specifiques (ex: PHARMACIE PRODUITS)')
    parser.add_argument('--cdc-only', action='store_true', help='4 tables CDC uniquement')
    parser.add_argument('--ref-only', action='store_true', help='14 tables reference uniquement')
    parser.add_argument('--chunk-size', type=int, default=10000, help='Taille chunks pandas (defaut: 10000)')
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

    logger.info(f"Bulk load: {len(tables)} tables, chunk_size={args.chunk_size}, truncate={args.truncate}")

    # Connexions
    mysql_conn = get_mysql_conn()
    sf_conn = get_snowflake_conn()

    grand_total = 0
    errors = []
    start_all = time.time()

    for mysql_table, sf_table in tables.items():
        try:
            rows = bulk_load_table(mysql_conn, sf_conn, mysql_table, sf_table, args.chunk_size, args.truncate)
            grand_total += rows
        except Exception as e:
            logger.error(f"ERREUR {mysql_table}: {e}")
            errors.append(mysql_table)
            continue

    elapsed_all = time.time() - start_all
    logger.info(f"Bulk load termine: {grand_total} rows, {len(tables)} tables, {elapsed_all:.1f}s")
    if errors:
        logger.warning(f"Tables en erreur: {errors}")
        sys.exit(1)

    mysql_conn.close()
    sf_conn.close()


if __name__ == '__main__':
    main()
