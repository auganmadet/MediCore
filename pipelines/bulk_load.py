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
import gc
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

import mysql.connector
import pandas as pd
import snowflake.connector


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Répertoire temporaire pour les fichiers Parquet
EXPORT_DIR = '/tmp/bulk_export'

# Stage Snowflake interne
STAGE_NAME = f'{os.getenv("SNOWFLAKE_DATABASE", "MEDICORE_PROD")}.RAW.BULK_STAGE'

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

# Tables candidates au mode incremental (grosses tables avec index sur date_col).
# Utilisees quand bulk_load.py est lance avec --incremental-days N : seuls les N
# derniers jours sont lus depuis MySQL puis MERGE dans Snowflake (au lieu du
# TRUNCATE+INSERT complet). Les tables absentes de ce mapping restent en mode
# classique meme avec --incremental-days.
#
# Cle = nom table MySQL ; valeurs :
#   - date_col : colonne MySQL utilisee pour filtrer la fenetre N jours
#   - pk_cols  : colonnes de la PK pour le MERGE INTO cote Snowflake
INCREMENTAL_TABLES: Dict[str, Dict[str, Any]] = {
    'MEDIPRIX_FACTURES': {
        'date_col': 'FAC_DATE',
        'pk_cols': ['PHA_ID', 'FAC_ID', 'FAC_TI'],
    },
    'STOCKHISTORY': {
        'date_col': 'STH_DATE',
        'pk_cols': ['PHA_ID', 'PRD_ID', 'STH_DATE'],
    },
    'DAYBYDAY': {
        'date_col': 'DBD_DATE',
        'pk_cols': ['PHA_ID', 'DBD_DATE', 'PRD_ID'],
    },
    'MANQHISTORY': {
        'date_col': 'MNQ_DATE',
        'pk_cols': ['PHA_ID', 'MNQ_DATE', 'PRD_ID', 'FAC_ID'],
    },
}


def get_mysql_conn() -> mysql.connector.MySQLConnection:
    """Connexion MySQL RDS avec timeout eleve pour bulk load.

    Returns:
        Connexion MySQL configuree avec timeouts etendus.
    """
    conn = mysql.connector.connect(
        host=os.getenv('MYSQL_HOST'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE', 'winstat'),
        connection_timeout=int(os.getenv('MYSQL_CONNECTION_TIMEOUT', '600')),
    )
    cursor = conn.cursor()
    cursor.execute("SET SESSION wait_timeout = 28800")
    cursor.execute("SET SESSION net_read_timeout = 600")
    cursor.execute("SET SESSION net_write_timeout = 600")
    cursor.close()
    return conn


def get_snowflake_conn() -> snowflake.connector.SnowflakeConnection:
    """Connexion Snowflake vers le schema RAW.

    Returns:
        Connexion Snowflake configuree pour le bulk load.
    """
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        role=os.getenv('SNOWFLAKE_ROLE_NAME', 'MEDICORE_RAW_WRITER'),
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        schema='RAW',
        insecure_mode=True  # Bypass OCSP pour PUT vers S3 stage
    )


def get_snowflake_columns(sf_conn: Any, table_name: str) -> Tuple[List[str], Set[str]]:
    """Recupere les noms de colonnes et types Snowflake (casing exact).

    Args:
        sf_conn: Connexion Snowflake active.
        table_name: Nom de la table a decrire.

    Returns:
        Tuple (liste_colonnes, ensemble_colonnes_boolean).
    """
    cursor = sf_conn.cursor()
    cursor.execute(f"DESCRIBE TABLE {table_name}")
    rows = cursor.fetchall()
    columns = [row[0] for row in rows]
    # Colonnes BOOLEAN : Parquet écrit int 0/1, Snowflake refuse variant→BOOLEAN
    bool_columns = {row[0] for row in rows if 'BOOLEAN' in str(row[1]).upper()}
    cursor.close()
    return columns, bool_columns


def ensure_stage(sf_conn: Any) -> None:
    """Cree le stage interne Snowflake s'il n'existe pas."""
    cursor = sf_conn.cursor()
    cursor.execute(f"CREATE STAGE IF NOT EXISTS {STAGE_NAME}")
    cursor.close()
    logger.info(f"Stage {STAGE_NAME} prêt")


def ensure_export_dir() -> None:
    """Cree le repertoire temporaire pour les fichiers Parquet."""
    os.makedirs(EXPORT_DIR, exist_ok=True)


def _write_chunk_to_stage(sf_cursor: Any, df: pd.DataFrame, sf_table: str, stage_path: str, chunk_num: int) -> float:
    """Ecrit un DataFrame en Parquet et le PUT vers le stage Snowflake.

    Args:
        sf_cursor: Curseur Snowflake actif.
        df: DataFrame a ecrire.
        sf_table: Nom de la table Snowflake cible.
        stage_path: Chemin du stage Snowflake.
        chunk_num: Numero du chunk (pour nommage fichier).

    Returns:
        Taille du fichier Parquet en Mo.
    """
    parquet_file = os.path.join(EXPORT_DIR, f"{sf_table}_{chunk_num:04d}.parquet")
    try:
        df.to_parquet(parquet_file, engine='pyarrow', index=False,
                      coerce_timestamps='us', allow_truncated_timestamps=True)
    except (OSError, MemoryError) as e:
        raise RuntimeError(f"[Parquet write] {sf_table} chunk {chunk_num} ({len(df)} rows): {e}") from e
    file_size_mb = os.path.getsize(parquet_file) / (1024 * 1024)

    put_query = f"PUT 'file://{parquet_file}' {stage_path} AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
    try:
        sf_cursor.execute(put_query)
    except snowflake.connector.errors.Error as e:
        raise RuntimeError(f"[PUT @stage] {sf_table} chunk {chunk_num} ({file_size_mb:.1f} Mo): {e}") from e

    os.remove(parquet_file)
    return file_size_mb


def _copy_into_and_cleanup(sf_cursor: Any, sf_table: str, stage_path: str, chunk_num: int, force: bool) -> float:
    """Execute COPY INTO depuis le stage, puis nettoie les fichiers.

    Args:
        sf_cursor: Curseur Snowflake actif.
        sf_table: Nom de la table Snowflake cible.
        stage_path: Chemin du stage Snowflake.
        chunk_num: Nombre de fichiers Parquet dans le stage.
        force: Si True, ajoute FORCE=TRUE pour ignorer le load metadata.

    Returns:
        Temps d'execution en secondes.
    """
    copy_start = time.time()
    force_clause = "FORCE = TRUE" if force else ""
    try:
        sf_cursor.execute(f"""
            COPY INTO {sf_table}
            FROM {stage_path}
            FILE_FORMAT = (TYPE = PARQUET USE_LOGICAL_TYPE = TRUE)
            MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
            {force_clause}
        """)
    except snowflake.connector.errors.Error as e:
        raise RuntimeError(f"[COPY INTO] {sf_table} ({chunk_num} fichiers): {e}") from e

    sf_cursor.execute(f"REMOVE {stage_path}")
    return time.time() - copy_start


def bulk_load_table(mysql_conn: Any, sf_conn: Any, mysql_table: str, sf_table: str, chunk_size: int, truncate: bool, force: bool = False) -> int:
    """Charge une table MySQL vers Snowflake RAW via Parquet + stage + COPY INTO.

    Flux : MySQL -> chunks -> Parquet local -> PUT @stage -> COPY INTO -> REMOVE.

    Args:
        mysql_conn: Connexion MySQL active.
        sf_conn: Connexion Snowflake active.
        mysql_table: Nom de la table MySQL source.
        sf_table: Nom de la table Snowflake cible.
        chunk_size: Nombre de lignes par fichier Parquet.
        truncate: Si True, TRUNCATE la table avant insertion.
        force: Si True, FORCE=TRUE dans COPY INTO.

    Returns:
        Nombre total de lignes chargees.
    """
    logger.info(f"{'='*60}")
    logger.info(f"Loading {mysql_table} -> {sf_table}...")
    start = time.time()

    # Curseur Snowflake réutilisé (évite fuite mémoire : 1 cursor par chunk = OOM)
    sf_cursor = sf_conn.cursor()

    # Pattern CLONE+SWAP : backup zero-copy avant TRUNCATE, rollback si echec
    backup_table = f"{sf_table}_BACKUP"
    has_backup = False
    if truncate:
        try:
            sf_cursor.execute(f"CREATE OR REPLACE TABLE {backup_table} CLONE {sf_table}")
            has_backup = True
            logger.info(f"  CLONE {sf_table} -> {backup_table}")
        except Exception as e:
            logger.warning(f"  CLONE echoue (premiere execution?) : {e}")
        sf_cursor.execute(f"TRUNCATE TABLE {sf_table}")
        logger.info(f"  TRUNCATE {sf_table}")

    # Colonnes Snowflake (casing exact + types BOOLEAN)
    sf_columns, sf_bool_columns = get_snowflake_columns(sf_conn, sf_table)
    sf_col_upper_map = {c.upper(): c for c in sf_columns}
    sf_col_set = set(sf_columns)

    # Nettoyer le sous-dossier stage pour cette table
    stage_path = f"@{STAGE_NAME}/{sf_table}/"
    sf_cursor.execute(f"REMOVE {stage_path}")

    # Lecture MySQL via curseur non-bufférisé (évite OOM sur tables volumineuses)
    # pd.read_sql(chunksize) buffèrise le résultat entier en mémoire avec mysql.connector
    MAX_RECONNECT = 10

    def mysql_open_cursor(conn, table, offset=0):
        """Ouvre un curseur MySQL non-bufférisé, avec OFFSET si reprise après déconnexion."""
        cur = conn.cursor(buffered=False)
        if offset > 0:
            cur.execute(f"SELECT * FROM `{table}` LIMIT 18446744073709551615 OFFSET {offset}")
        else:
            cur.execute(f"SELECT * FROM `{table}`")
        return cur

    current_mysql_conn = mysql_conn
    cursor_mysql = mysql_open_cursor(current_mysql_conn, mysql_table)
    col_names = [desc[0] for desc in cursor_mysql.description]

    total_rows = 0
    chunk_num = 0
    reconnect_count = 0

    while True:
        # Lecture avec reconnexion automatique en cas de perte de connexion MySQL
        try:
            rows = cursor_mysql.fetchmany(chunk_size)
        except (mysql.connector.errors.OperationalError,
                mysql.connector.errors.InterfaceError,
                mysql.connector.errors.DatabaseError) as e:
            reconnect_count += 1
            if reconnect_count > MAX_RECONNECT:
                raise RuntimeError(f"Abandon après {MAX_RECONNECT} reconnexions MySQL") from e
            logger.warning(f"  MySQL déconnecté au row {total_rows}: {e}")
            # Fermer proprement l'ancienne connexion
            try:
                cursor_mysql.close()
            except (mysql.connector.errors.Error, OSError):
                logger.debug("Fermeture curseur MySQL echouee (connexion perdue)")
            try:
                current_mysql_conn.close()
            except (mysql.connector.errors.Error, OSError):
                logger.debug("Fermeture connexion MySQL echouee (connexion perdue)")
            # Reconnexion avec backoff
            for attempt in range(1, 6):
                try:
                    logger.info(f"  Reconnexion MySQL (tentative {attempt}/5, reprise offset={total_rows})...")
                    time.sleep(5 * attempt)
                    current_mysql_conn = get_mysql_conn()
                    cursor_mysql = mysql_open_cursor(current_mysql_conn, mysql_table, offset=total_rows)
                    logger.info(f"  Reconnecté, reprise à la ligne {total_rows}")
                    break
                except (mysql.connector.errors.Error, OSError) as re_err:
                    logger.warning(f"  Tentative {attempt} echouee: {re_err}")
            else:
                raise RuntimeError("Impossible de se reconnecter a MySQL apres 5 tentatives")
            continue

        if not rows:
            break

        chunk_num += 1
        chunk_start = time.time()

        df = pd.DataFrame(rows, columns=col_names)

        # Renommer colonnes MySQL → casing Snowflake
        df.columns = [sf_col_upper_map.get(c.upper(), c.upper()) for c in df.columns]

        # Ajouter métadonnées CDC (3 colonnes : alignement avec les 4 tables RAW_* CDC)
        now = datetime.now()
        cdc_metadata = {
            'CDC_OPERATION': 'S',
            'CDC_TIMESTAMP': now,
            'CDC_LSN': None,
        }
        for col_upper, value in cdc_metadata.items():
            sf_col_name = sf_col_upper_map.get(col_upper)
            if sf_col_name and sf_col_name in sf_col_set:
                df[sf_col_name] = value

        # Convertir colonnes BOOLEAN (MySQL TINYINT 0/1 → Python bool pour Parquet)
        for bc in sf_bool_columns:
            if bc in df.columns:
                df[bc] = df[bc].astype(bool)

        # Ne garder que les colonnes existantes dans Snowflake
        valid_cols = [c for c in df.columns if c in sf_col_set]
        df = df[valid_cols]

        # Parquet local + PUT vers stage Snowflake
        file_size_mb = _write_chunk_to_stage(sf_cursor, df, sf_table, stage_path, chunk_num)

        total_rows += len(df)
        chunk_time = time.time() - chunk_start
        logger.info(f"  Chunk {chunk_num}: {len(df)} rows, {file_size_mb:.1f} Mo, PUT {chunk_time:.1f}s | Total: {total_rows}")

        # Libérer mémoire explicitement
        del df, rows
        gc.collect()

    cursor_mysql.close()
    # Fermer la connexion MySQL si elle a été recréée par reconnexion
    if current_mysql_conn is not mysql_conn:
        current_mysql_conn.close()

    if total_rows == 0:
        logger.warning(f"  {sf_table}: table vide (0 rows)")
        return 0

    # COPY INTO : 1 seule operation pour tous les fichiers Parquet du stage
    logger.info(f"  COPY INTO {sf_table} depuis {stage_path} ({chunk_num} fichiers)...")
    copy_time = _copy_into_and_cleanup(sf_cursor, sf_table, stage_path, chunk_num, force)
    logger.info(f"  COPY INTO termine en {copy_time:.1f}s")

    # Pattern CLONE+SWAP : verification post-load + cleanup ou rollback
    if has_backup and truncate:
        if total_rows > 0:
            # Load OK -> supprimer le backup
            try:
                sf_cursor.execute(f"DROP TABLE IF EXISTS {backup_table}")
                logger.info(f"  Backup {backup_table} supprime (load OK)")
            except Exception:
                pass
        else:
            # Load vide -> rollback : SWAP le backup en place
            logger.warning(f"  {sf_table} vide apres load — rollback depuis {backup_table}")
            try:
                sf_cursor.execute(f"ALTER TABLE {backup_table} SWAP WITH {sf_table}")
                sf_cursor.execute(f"DROP TABLE IF EXISTS {backup_table}")
                logger.info(f"  Rollback OK — {sf_table} restaure depuis le backup")
            except Exception as e:
                logger.error(f"  Rollback echoue : {e}")

    sf_cursor.close()

    elapsed = time.time() - start
    logger.info(f"  {sf_table}: {total_rows} rows en {elapsed:.1f}s ({chunk_num} fichiers Parquet)")
    return total_rows


def bulk_load_incremental_table(mysql_conn: Any, sf_conn: Any, mysql_table: str,
                                sf_table: str, date_col: str, pk_cols: List[str],
                                days_window: int, chunk_size: int) -> int:
    """Charge les N derniers jours depuis MySQL et MERGE dans Snowflake.

    Mode incremental : au lieu de TRUNCATE+reload toute la table, on lit
    uniquement les lignes MySQL dont date_col >= CURDATE() - N days, puis on
    MERGE dans la table cible sur la PK (UPDATE si match, INSERT sinon).

    Flux :
      1. CREATE OR REPLACE TABLE {sf_table}_STG_INCR LIKE {sf_table}
      2. SELECT MySQL filtre sur date_col -> chunks Parquet -> stage
      3. COPY INTO staging
      4. MERGE INTO cible FROM staging (sur pk_cols)
      5. DROP staging

    Args:
        mysql_conn: Connexion MySQL active.
        sf_conn: Connexion Snowflake active.
        mysql_table: Nom de la table MySQL source.
        sf_table: Nom de la table Snowflake cible.
        date_col: Colonne MySQL servant au filtre (ex: 'FAC_DATE').
        pk_cols: Colonnes de la clef primaire pour le MERGE.
        days_window: Fenetre glissante en jours (ex: 30).
        chunk_size: Lignes par fichier Parquet.

    Returns:
        Nombre total de lignes lues depuis MySQL (= charges en staging).
    """
    logger.info(f"{'='*60}")
    logger.info(f"Loading INCREMENTAL {mysql_table} -> {sf_table} "
                f"(fenetre {days_window}j sur {date_col})...")
    start = time.time()

    sf_cursor = sf_conn.cursor()
    staging_table = f"{sf_table}_STG_INCR"

    # 1. Creer la table staging temporaire (meme schema que la cible, sans donnees)
    sf_cursor.execute(f"CREATE OR REPLACE TABLE {staging_table} LIKE {sf_table}")
    logger.info(f"  CREATE OR REPLACE {staging_table} LIKE {sf_table}")

    # Colonnes Snowflake (casing exact + types BOOLEAN)
    sf_columns, sf_bool_columns = get_snowflake_columns(sf_conn, sf_table)
    sf_col_upper_map = {c.upper(): c for c in sf_columns}
    sf_col_set = set(sf_columns)

    stage_path = f"@{STAGE_NAME}/{staging_table}/"
    sf_cursor.execute(f"REMOVE {stage_path}")

    # 2. Lire MySQL avec WHERE sur date (index presume sur date_col)
    where_clause = f"`{date_col}` >= DATE_SUB(CURDATE(), INTERVAL {days_window} DAY)"
    cursor_mysql = mysql_conn.cursor(buffered=False)
    cursor_mysql.execute(f"SELECT * FROM `{mysql_table}` WHERE {where_clause}")
    col_names = [desc[0] for desc in cursor_mysql.description]

    total_rows = 0
    chunk_num = 0

    while True:
        rows = cursor_mysql.fetchmany(chunk_size)
        if not rows:
            break
        chunk_num += 1
        chunk_start = time.time()

        df = pd.DataFrame(rows, columns=col_names)
        df.columns = [sf_col_upper_map.get(c.upper(), c.upper()) for c in df.columns]

        # Metadonnees CDC (alignees avec bulk_load_table : source = snapshot)
        now = datetime.now()
        cdc_metadata = {'CDC_OPERATION': 'S', 'CDC_TIMESTAMP': now, 'CDC_LSN': None}
        for col_upper, value in cdc_metadata.items():
            sf_col_name = sf_col_upper_map.get(col_upper)
            if sf_col_name and sf_col_name in sf_col_set:
                df[sf_col_name] = value

        for bc in sf_bool_columns:
            if bc in df.columns:
                df[bc] = df[bc].astype(bool)

        valid_cols = [c for c in df.columns if c in sf_col_set]
        df = df[valid_cols]

        file_size_mb = _write_chunk_to_stage(sf_cursor, df, staging_table, stage_path, chunk_num)
        total_rows += len(df)
        chunk_time = time.time() - chunk_start
        logger.info(f"  Chunk {chunk_num}: {len(df)} rows, {file_size_mb:.1f} Mo, "
                    f"PUT {chunk_time:.1f}s | Total: {total_rows}")

        del df, rows
        gc.collect()

    cursor_mysql.close()

    if total_rows == 0:
        logger.info(f"  Aucune ligne sur les {days_window} derniers jours — MERGE skippe")
        try:
            sf_cursor.execute(f"DROP TABLE IF EXISTS {staging_table}")
        except Exception:  # pylint: disable=broad-except
            pass
        sf_cursor.close()
        return 0

    # 3. COPY INTO staging (FORCE=TRUE car table fraichement creee)
    logger.info(f"  COPY INTO {staging_table} depuis {stage_path} ({chunk_num} fichiers)...")
    copy_time = _copy_into_and_cleanup(sf_cursor, staging_table, stage_path, chunk_num, force=True)
    logger.info(f"  COPY INTO termine en {copy_time:.1f}s")

    # 4. MERGE INTO cible depuis staging
    pk_upper = {p.upper() for p in pk_cols}
    non_pk_cols = [c for c in sf_columns if c.upper() not in pk_upper]

    pk_join = ' AND '.join(f'tgt."{c}" = src."{c}"' for c in pk_cols)
    update_set = ', '.join(f'tgt."{c}" = src."{c}"' for c in non_pk_cols)
    insert_cols = ', '.join(f'"{c}"' for c in sf_columns)
    insert_vals = ', '.join(f'src."{c}"' for c in sf_columns)

    merge_sql = (
        f"MERGE INTO {sf_table} tgt "
        f"USING {staging_table} src ON {pk_join} "
        f"WHEN MATCHED THEN UPDATE SET {update_set} "
        f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
    )
    logger.info(f"  MERGE INTO {sf_table} ON PK={pk_cols}...")
    merge_start = time.time()
    sf_cursor.execute(merge_sql)
    merge_result = sf_cursor.fetchone()
    merge_time = time.time() - merge_start
    # Snowflake renvoie (rows_inserted, rows_updated) selon la version du driver
    logger.info(f"  MERGE termine en {merge_time:.1f}s — result={merge_result}")

    # 5. DROP staging
    try:
        sf_cursor.execute(f"DROP TABLE IF EXISTS {staging_table}")
        logger.info(f"  DROP {staging_table}")
    except Exception as e:  # pylint: disable=broad-except
        logger.warning(f"  DROP {staging_table} echoue (non bloquant): {e}")

    sf_cursor.close()
    elapsed = time.time() - start
    logger.info(f"  {sf_table}: {total_rows} rows en staging, merge en {elapsed:.1f}s "
                f"({chunk_num} fichiers Parquet)")
    return total_rows


LOCK_FILE = '/tmp/bulk_load.lock'


def acquire_lock() -> None:
    """Pose un lock file pour empecher la boucle batch de tourner pendant le bulk load."""
    with open(LOCK_FILE, 'w') as f:
        f.write(f"{os.getpid()} {datetime.now().isoformat()}")
    logger.info(f"Lock acquis: {LOCK_FILE}")


def release_lock() -> None:
    """Retire le lock file."""
    try:
        os.remove(LOCK_FILE)
        logger.info(f"Lock libere: {LOCK_FILE}")
    except FileNotFoundError:
        pass


def main() -> None:
    """Point d'entree : bulk load MySQL -> Snowflake RAW via Parquet + stage."""
    parser = argparse.ArgumentParser(description='Bulk load MySQL RDS -> Snowflake RAW (18 tables) via Parquet + stage')
    parser.add_argument('--tables', nargs='+', help='Tables specifiques (ex: PHARMACIE PRODUITS)')
    parser.add_argument('--cdc-only', action='store_true', help='4 tables CDC uniquement')
    parser.add_argument('--ref-only', action='store_true', help='14 tables reference uniquement')
    parser.add_argument('--chunk-size', type=int, default=500000, help='Lignes par fichier Parquet (defaut: 500000)')
    parser.add_argument('--truncate', action='store_true', help='TRUNCATE TABLE avant insertion')
    parser.add_argument('--incremental-days', type=int, default=None,
                        help='Si fourni, les tables eligibles (INCREMENTAL_TABLES) sont '
                             'chargees en MERGE sur les N derniers jours au lieu de '
                             'TRUNCATE+INSERT. Les autres tables restent en mode classique.')
    parser.add_argument('--run-id', default=None, help='Pipeline run ID pour audit')
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

    # Poser le lock pour bloquer la boucle batch
    acquire_lock()

    logger.info(f"{'='*60}")
    logger.info(f"Bulk load: {len(tables)} tables, chunk_size={args.chunk_size:,}, truncate={args.truncate}")
    logger.info(f"Methode: Parquet + PUT @{STAGE_NAME} + COPY INTO")
    logger.info(f"{'='*60}")

    try:
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
            mysql_conn = None
            try:
                mysql_conn = get_mysql_conn()
                # Mode incremental pour les tables eligibles si --incremental-days fourni
                if args.incremental_days and mysql_table in INCREMENTAL_TABLES:
                    conf = INCREMENTAL_TABLES[mysql_table]
                    rows = bulk_load_incremental_table(
                        mysql_conn, sf_conn, mysql_table, sf_table,
                        conf['date_col'], conf['pk_cols'],
                        args.incremental_days, args.chunk_size,
                    )
                else:
                    rows = bulk_load_table(mysql_conn, sf_conn, mysql_table, sf_table,
                                           args.chunk_size, args.truncate,
                                           force=args.truncate)
                grand_total += rows
                results.append((sf_table, rows))
            except (RuntimeError, mysql.connector.errors.Error, snowflake.connector.errors.Error, OSError) as e:
                logger.error(f"ERREUR {mysql_table}: {e}")
                errors.append(mysql_table)
            finally:
                if mysql_conn:
                    mysql_conn.close()

        elapsed_all = time.time() - start_all

        # Résumé final
        logger.info(f"{'='*60}")
        logger.info("RESUME BULK LOAD")
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

    finally:
        # Toujours liberer le lock, meme en cas d'erreur
        release_lock()


if __name__ == '__main__':
    main()
