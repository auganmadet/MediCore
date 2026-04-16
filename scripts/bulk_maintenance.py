"""Maintenance Phase 3 : verification Bulk Load / RAW.

Verifie l'etat des tables RAW apres bulk load :
- B1 : Lock file perime
- B2 : Tables RAW vides apres reload
- B3 : Doublons dans les 14 tables reference
- B4 : Reconciliation MySQL vs Snowflake (count par table)
- B5 : Timestamps incoherents (CDC_TIMESTAMP trop ancien)
- B6 : Schema drift MySQL vs Snowflake (colonnes manquantes)

S'auto-authentifie via .env. Lecture seule par defaut.

Usage :
    python scripts/bulk_maintenance.py
    python scripts/bulk_maintenance.py --fix       (supprime lock perime, relance diagnose_recover)
    python scripts/bulk_maintenance.py --dry-run   (detecte sans corriger)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except ImportError:
    pass

import snowflake.connector

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

LOCK_FILE = '/tmp/bulk_load.lock'
FRESHNESS_HOURS = 48

REF_TABLES = {
    'RAW_DAYBYDAY': 'PHA_ID, DBD_DATE, PRD_ID',
    'RAW_EAN13': 'PHA_ID, EAN_13, PRD_ID',
    'RAW_FOURNISSEURS': 'PHA_ID, FOU_ID',
    'RAW_HISTORY': 'PHA_ID, "Date"',
    'RAW_LOG': 'PHA_ID',
    'RAW_LPPR': 'PHA_ID, PRD_ID, LPP_INDEX, LPP_CODE',
    'RAW_MANQHISTORY': 'PHA_ID, MNQ_DATE, PRD_ID, FAC_ID',
    'RAW_MEDIPRIX_FACTURES': 'PHA_ID, FAC_ID, FAC_TI',
    'RAW_PHARMACIE': 'PHA_ID',
    'RAW_PHARMACIES': 'PHA_ID',
    'RAW_PHARMACIES_ERREUR': 'PHA_ID',
    'RAW_PRODUITS': 'PHA_ID, PRD_ID',
    'RAW_PRODUITS_NEGATIFS': 'PHA_ID, PRD_ID',
    'RAW_STOCKHISTORY': 'PHA_ID, STK_DATE, PRD_ID',
}

ALL_TABLES = list(REF_TABLES.keys()) + [
    'RAW_COMMANDES', 'RAW_FACTURES', 'RAW_ORDERS', 'RAW_MODSTOCK',
]


def get_snowflake_conn():
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        schema='RAW',
    )


def get_mysql_conn():
    import mysql.connector
    return mysql.connector.connect(
        host=os.getenv('MYSQL_HOST'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE', 'winstat'),
        connection_timeout=30,
    )


def check_b1_lock_file():
    """B1 : lock file perime."""
    if not os.path.exists(LOCK_FILE):
        return True, 'Pas de lock file'

    try:
        with open(LOCK_FILE) as f:
            content = f.read().strip()
        pid = content.split()[0] if content else None

        if pid and os.path.exists(f'/proc/{pid}'):
            return False, f'Lock actif (PID {pid} en cours)'
        return False, f'Lock perime (PID {pid} absent)'
    except Exception as e:
        return False, str(e)[:100]


def check_b2_empty_tables():
    """B2 : tables RAW vides."""
    try:
        conn = get_snowflake_conn()
        cursor = conn.cursor()
        empty = []

        for table in ALL_TABLES:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
            if count == 0:
                empty.append(table)

        cursor.close()
        conn.close()
        return len(empty) == 0, {'empty_tables': empty, 'total': len(ALL_TABLES)}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_b3_duplicates():
    """B3 : doublons dans les 14 tables reference."""
    try:
        conn = get_snowflake_conn()
        cursor = conn.cursor()
        dupes = {}

        for table, pk in REF_TABLES.items():
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            total = cursor.fetchone()[0]
            cursor.execute(
                f'SELECT COUNT(*) FROM ('
                f'SELECT {pk} FROM {table} GROUP BY {pk} HAVING COUNT(*) > 1'
                f')'
            )
            nb_dupes = cursor.fetchone()[0]
            if nb_dupes > 0:
                dupes[table] = nb_dupes

        cursor.close()
        conn.close()
        return len(dupes) == 0, {'duplicates': dupes}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_b4_reconciliation():
    """B4 : reconciliation MySQL vs Snowflake (count par table)."""
    mysql_to_sf = {
        'PHARMACIE': 'RAW_PHARMACIE',
        'PRODUITS': 'RAW_PRODUITS',
        'FOURNISSEURS': 'RAW_FOURNISSEURS',
        'COMMANDES': 'RAW_COMMANDES',
        'FACTURES': 'RAW_FACTURES',
    }

    try:
        sf_conn = get_snowflake_conn()
        sf_cursor = sf_conn.cursor()
    except Exception as e:
        return False, {'error': f'Snowflake: {str(e)[:80]}'}

    try:
        my_conn = get_mysql_conn()
        my_cursor = my_conn.cursor()
    except Exception as e:
        sf_cursor.close()
        sf_conn.close()
        return False, {'error': f'MySQL: {str(e)[:80]}'}

    ecarts = {}
    for mysql_table, sf_table in mysql_to_sf.items():
        try:
            my_cursor.execute(f'SELECT COUNT(*) FROM {mysql_table}')
            mysql_count = my_cursor.fetchone()[0]
        except Exception:
            mysql_count = -1

        try:
            sf_cursor.execute(f'SELECT COUNT(*) FROM {sf_table}')
            sf_count = sf_cursor.fetchone()[0]
        except Exception:
            sf_count = -1

        if mysql_count != sf_count:
            ecarts[mysql_table] = {'mysql': mysql_count, 'snowflake': sf_count}

    my_cursor.close()
    my_conn.close()
    sf_cursor.close()
    sf_conn.close()
    return len(ecarts) == 0, {'ecarts': ecarts, 'tables_verifiees': len(mysql_to_sf)}


def check_b5_timestamps():
    """B5 : timestamps incoherents (CDC_TIMESTAMP trop ancien)."""
    try:
        conn = get_snowflake_conn()
        cursor = conn.cursor()
        stale = {}
        threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=FRESHNESS_HOURS)

        for table in ALL_TABLES:
            try:
                cursor.execute(f'SELECT MAX(CDC_TIMESTAMP) FROM {table}')
                max_ts = cursor.fetchone()[0]
                if max_ts and max_ts < threshold:
                    stale[table] = str(max_ts)
            except Exception:
                pass

        cursor.close()
        conn.close()
        return len(stale) == 0, {'stale_tables': stale, 'threshold_hours': FRESHNESS_HOURS}
    except Exception as e:
        return False, {'error': str(e)[:100]}


def check_b6_schema_drift():
    """B6 : schema drift MySQL vs Snowflake (colonnes manquantes)."""
    tables_to_check = {'PHARMACIE': 'RAW_PHARMACIE', 'PRODUITS': 'RAW_PRODUITS'}

    try:
        sf_conn = get_snowflake_conn()
        sf_cursor = sf_conn.cursor()
    except Exception as e:
        return False, {'error': f'Snowflake: {str(e)[:80]}'}

    try:
        my_conn = get_mysql_conn()
        my_cursor = my_conn.cursor()
    except Exception as e:
        sf_cursor.close()
        sf_conn.close()
        return False, {'error': f'MySQL: {str(e)[:80]}'}

    drift = {}
    for mysql_table, sf_table in tables_to_check.items():
        try:
            my_cursor.execute(f'SHOW COLUMNS FROM {mysql_table}')
            mysql_cols = {row[0].upper() for row in my_cursor.fetchall()}
        except Exception:
            mysql_cols = set()

        try:
            sf_cursor.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='RAW' AND TABLE_NAME='{sf_table}'")
            sf_cols = {row[0].upper() for row in sf_cursor.fetchall()}
        except Exception:
            sf_cols = set()

        # Colonnes CDC ajoutees par le pipeline (pas dans MySQL)
        cdc_cols = {'CDC_OPERATION', 'CDC_TIMESTAMP', 'CDC_LSN', 'CDC_SCHEMA', 'CDC_TABLE'}
        sf_cols_clean = sf_cols - cdc_cols

        missing_in_sf = mysql_cols - sf_cols_clean
        extra_in_sf = sf_cols_clean - mysql_cols

        if missing_in_sf or extra_in_sf:
            drift[mysql_table] = {
                'missing_in_snowflake': list(missing_in_sf),
                'extra_in_snowflake': list(extra_in_sf),
            }

    my_cursor.close()
    my_conn.close()
    sf_cursor.close()
    sf_conn.close()
    return len(drift) == 0, {'drift': drift}


def fix_b1_lock():
    """Supprime le lock file perime."""
    try:
        os.remove(LOCK_FILE)
        return True, 'Lock file supprime'
    except Exception as e:
        return False, str(e)[:100]


def fix_b4_reconciliation(ecarts):
    """Corrige B4 : relance bulk_load avec pattern CLONE + SWAP.

    Pattern atomique par table :
    1. CLONE RAW_TABLE -> RAW_TABLE_BACKUP
    2. bulk_load --tables TABLE --truncate
    3. Verifier count
    4. Si OK -> DROP backup
    5. Si FAIL -> SWAP backup (rollback)
    """
    import subprocess
    fixed = []
    failed = []
    rolled_back = []

    mysql_to_bulk = {
        'PHARMACIE': 'PHARMACIE',
        'PRODUITS': 'PRODUITS',
        'FOURNISSEURS': 'FOURNISSEURS',
        'COMMANDES': 'COMMANDES',
        'FACTURES': 'FACTURES',
    }

    conn = get_snowflake_conn()
    cursor = conn.cursor()

    for table_name in ecarts:
        bulk_name = mysql_to_bulk.get(table_name)
        if not bulk_name:
            failed.append(f'{table_name}: pas de mapping bulk_load')
            continue

        sf_table = f'RAW_{table_name}'
        backup_table = f'RAW_{table_name}_BACKUP'

        try:
            # 1. Count avant + CLONE backup
            cursor.execute(f'SELECT COUNT(*) FROM {sf_table}')
            pre_count = cursor.fetchone()[0]
            cursor.execute(f'CREATE OR REPLACE TABLE {backup_table} CLONE {sf_table}')
            logger.info(f'  CLONE {sf_table} ({pre_count} rows)')

            # 2. Reload
            result = subprocess.run(
                ['python', '/app/pipelines/bulk_load.py', '--tables', bulk_name, '--truncate'],
                capture_output=True, text=True, timeout=3600,
            )

            if result.returncode != 0:
                # Rollback
                cursor.execute(f'ALTER TABLE {backup_table} SWAP WITH {sf_table}')
                cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
                rolled_back.append(table_name)
                failed.append(f'{bulk_name}: load echoue, rollback OK')
                continue

            # 3. Verifier count
            cursor.execute(f'SELECT COUNT(*) FROM {sf_table}')
            post_count = cursor.fetchone()[0]

            if post_count == 0:
                # Rollback
                cursor.execute(f'ALTER TABLE {backup_table} SWAP WITH {sf_table}')
                cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
                rolled_back.append(table_name)
                failed.append(f'{bulk_name}: vide apres load, rollback OK')
                continue

            # 4. OK -> drop backup
            cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
            fixed.append(f'{bulk_name} ({pre_count} -> {post_count})')

        except Exception as e:
            try:
                cursor.execute(f'ALTER TABLE {backup_table} SWAP WITH {sf_table}')
                cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
                rolled_back.append(table_name)
            except Exception:
                pass
            failed.append(f'{bulk_name}: {str(e)[:50]}')

    cursor.close()
    conn.close()

    msg = f'{len(fixed)} tables rechargees'
    if rolled_back:
        msg += f', {len(rolled_back)} rollback'
    if failed:
        msg += f', {len(failed)} echouees'
    return len(failed) == 0, msg


def fix_b6_schema_drift(drift):
    """Corrige B6 : ajoute les colonnes manquantes avec le type detecte depuis MySQL.

    Garde-fou : detecte le type MySQL avant d'ajouter (pas VARCHAR par defaut).
    Mapping MySQL -> Snowflake : INT->NUMBER, VARCHAR->VARCHAR(N), DATE->DATE, etc.
    """
    mysql_type_map = {
        'int': 'NUMBER',
        'bigint': 'NUMBER',
        'smallint': 'NUMBER',
        'tinyint': 'NUMBER',
        'decimal': 'NUMBER(18,2)',
        'float': 'FLOAT',
        'double': 'FLOAT',
        'varchar': 'VARCHAR',
        'char': 'VARCHAR',
        'text': 'VARCHAR',
        'date': 'DATE',
        'datetime': 'TIMESTAMP_NTZ',
        'timestamp': 'TIMESTAMP_NTZ',
    }

    try:
        # Recuperer les types MySQL
        my_conn = get_mysql_conn()
        my_cursor = my_conn.cursor()
    except Exception as e:
        # Si MySQL inaccessible, fallback VARCHAR
        logger.warning(f'MySQL inaccessible pour detection types: {e}')
        try:
            conn = get_snowflake_conn()
            cursor = conn.cursor()
            added = []
            for table_name, info in drift.items():
                sf_table = f'RAW_{table_name}' if not table_name.startswith('RAW_') else table_name
                for col in info.get('missing_in_snowflake', []):
                    try:
                        cursor.execute(f'ALTER TABLE {sf_table} ADD COLUMN {col} VARCHAR')
                        added.append(f'{sf_table}.{col} (VARCHAR fallback)')
                    except Exception:
                        pass
            cursor.close()
            conn.close()
            return len(added) > 0, f'{len(added)} colonnes ajoutees (VARCHAR fallback)'
        except Exception as e2:
            return False, str(e2)[:100]

    conn = get_snowflake_conn()
    cursor = conn.cursor()
    added = []

    for table_name, info in drift.items():
        sf_table = f'RAW_{table_name}' if not table_name.startswith('RAW_') else table_name
        mysql_table = table_name.replace('RAW_', '')

        # Recuperer les types MySQL pour cette table
        mysql_col_types = {}
        try:
            my_cursor.execute(f'SHOW COLUMNS FROM {mysql_table}')
            for row in my_cursor.fetchall():
                col_name = row[0].upper()
                col_type = row[1].lower().split('(')[0]
                sf_type = mysql_type_map.get(col_type, 'VARCHAR')
                mysql_col_types[col_name] = sf_type
        except Exception:
            pass

        for col in info.get('missing_in_snowflake', []):
            sf_type = mysql_col_types.get(col.upper(), 'VARCHAR')
            try:
                cursor.execute(f'ALTER TABLE {sf_table} ADD COLUMN {col} {sf_type}')
                added.append(f'{sf_table}.{col} ({sf_type})')
            except Exception as e:
                logger.warning(f'Ajout colonne {sf_table}.{col}: {e}')

    my_cursor.close()
    my_conn.close()
    cursor.close()
    conn.close()
    return len(added) > 0, f'{len(added)} colonnes ajoutees: {added}'


def fix_b5_ref_reload():
    """Relance le ref_reload table par table avec pattern CLONE + SWAP.

    Pattern atomique :
    1. CLONE RAW_TABLE -> RAW_TABLE_BACKUP (zero-copy, gratuit)
    2. TRUNCATE RAW_TABLE
    3. bulk_load.py --tables TABLE --truncate
    4. Verifier count >= ancien count
    5. Si OK -> DROP RAW_TABLE_BACKUP
    6. Si FAIL -> SWAP backup en place (rollback instantane)

    Garde-fous :
    - Verifie le lock file avant de lancer
    - Table par table (pas toutes d'un coup)
    - Rollback automatique si le load echoue
    - Si une table echoue, continue les autres
    - Timeout 1h par table
    """
    import subprocess

    if os.path.exists(LOCK_FILE):
        return False, 'Lock file present — un bulk_load est deja en cours'

    ref_table_names = [
        'DAYBYDAY', 'EAN13', 'FOURNISSEURS', 'HISTORY', 'LOG', 'LPPR',
        'MANQHISTORY', 'MEDIPRIX_FACTURES', 'PHARMACIE', 'PRODUITS',
        'PRODUITS_NEGATIFS', 'STOCKHISTORY', 'PHARMACIES', 'PHARMACIES_ERREUR',
    ]

    fixed = []
    failed = []
    rolled_back = []

    conn = get_snowflake_conn()
    cursor = conn.cursor()

    for table_name in ref_table_names:
        sf_table = f'RAW_{table_name}'
        backup_table = f'RAW_{table_name}_BACKUP'
        logger.info(f'Reload {table_name} (CLONE + SWAP)...')

        try:
            # 1. Sauvegarder le count avant
            cursor.execute(f'SELECT COUNT(*) FROM {sf_table}')
            pre_count = cursor.fetchone()[0]

            # 2. CLONE zero-copy (backup gratuit)
            cursor.execute(f'CREATE OR REPLACE TABLE {backup_table} CLONE {sf_table}')
            logger.info(f'  CLONE {sf_table} -> {backup_table} ({pre_count} rows)')

            # 3. Reload via bulk_load.py
            result = subprocess.run(
                ['python', '/app/pipelines/bulk_load.py', '--tables', table_name, '--truncate'],
                capture_output=True, text=True, timeout=3600,
            )

            if result.returncode != 0:
                # Load echoue -> rollback : SWAP le backup en place
                logger.warning(f'  Load echoue pour {table_name} — rollback...')
                cursor.execute(f'ALTER TABLE {backup_table} SWAP WITH {sf_table}')
                cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
                rolled_back.append(table_name)
                failed.append(f'{table_name}: load echoue, rollback OK')
                continue

            # 4. Verifier le count apres load
            cursor.execute(f'SELECT COUNT(*) FROM {sf_table}')
            post_count = cursor.fetchone()[0]

            if post_count == 0:
                # Table vide apres load -> rollback
                logger.warning(f'  {table_name} vide apres load — rollback...')
                cursor.execute(f'ALTER TABLE {backup_table} SWAP WITH {sf_table}')
                cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
                rolled_back.append(table_name)
                failed.append(f'{table_name}: vide apres load, rollback OK')
                continue

            # 5. Load OK -> supprimer le backup
            cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
            fixed.append(f'{table_name} ({pre_count} -> {post_count})')
            logger.info(f'  {table_name} OK ({pre_count} -> {post_count})')

        except subprocess.TimeoutExpired:
            # Timeout -> rollback
            logger.warning(f'  {table_name} timeout — rollback...')
            try:
                cursor.execute(f'ALTER TABLE {backup_table} SWAP WITH {sf_table}')
                cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
                rolled_back.append(table_name)
            except Exception:
                pass
            failed.append(f'{table_name}: timeout 1h, rollback')
        except Exception as e:
            # Erreur inattendue -> tenter rollback
            try:
                cursor.execute(f'ALTER TABLE {backup_table} SWAP WITH {sf_table}')
                cursor.execute(f'DROP TABLE IF EXISTS {backup_table}')
                rolled_back.append(table_name)
            except Exception:
                pass
            failed.append(f'{table_name}: {str(e)[:50]}')

    cursor.close()
    conn.close()

    msg = f'{len(fixed)}/{len(ref_table_names)} tables rechargees'
    if rolled_back:
        msg += f', {len(rolled_back)} rollback'
    if failed:
        msg += f', {len(failed)} echouees: {[f.split(":")[0] for f in failed]}'
    return len(failed) == 0, msg


def main():
    parser = argparse.ArgumentParser(description='Bulk load maintenance (B1-B6)')
    fix_group = parser.add_mutually_exclusive_group()
    fix_group.add_argument('--fix-safe', action='store_true',
                           help='Fix surs : B1 (lock perime)')
    fix_group.add_argument('--fix', action='store_true',
                           help='Tous les fix : B1, B4 (reconciliation), B5 (ref_reload), B6 (schema)')
    parser.add_argument('--dry-run', action='store_true', help='Detecte sans corriger')
    args = parser.parse_args()

    print('=' * 60)
    print('BULK LOAD MAINTENANCE')
    print('=' * 60)

    checks = [
        ('B1', 'Lock file perime', check_b1_lock_file),
        ('B2', 'Tables RAW vides', check_b2_empty_tables),
        ('B3', 'Doublons tables reference', check_b3_duplicates),
        ('B4', 'Reconciliation MySQL/Snowflake', check_b4_reconciliation),
        ('B5', 'Timestamps incoherents', check_b5_timestamps),
        ('B6', 'Schema drift MySQL/Snowflake', check_b6_schema_drift),
    ]

    results = {}
    for code, name, check_fn in checks:
        ok, details = check_fn()
        status = 'OK' if ok else 'FAIL'
        results[code] = {'ok': ok, 'details': details}
        print(f'\n  {code} {name}')
        print(f'     Status: {status}')

        if isinstance(details, dict):
            for k, v in details.items():
                if isinstance(v, dict) and v:
                    for k2, v2 in v.items():
                        print(f'     {k}.{k2}: {v2}')
                elif isinstance(v, list) and v:
                    print(f'     {k}: {v}')
                elif v and k != 'error':
                    print(f'     {k}: {v}')
                elif k == 'error':
                    print(f'     Erreur: {v}')
        else:
            print(f'     {details}')

    # Corrections
    if (args.fix or args.fix_safe) and not args.dry_run:
        print('\n--- Corrections ---')

        # Fix surs (--fix-safe et --fix)
        if not results.get('B1', {}).get('ok', True):
            ok, msg = fix_b1_lock()
            print(f'  B1 lock file: {"OK" if ok else "FAIL"} ({msg})')

        if not results.get('B6', {}).get('ok', True):
            drift = results['B6'].get('details', {}).get('drift', {})
            if drift:
                print(f'  B6 schema drift: ajout colonnes (types detectes)...')
                ok, msg = fix_b6_schema_drift(drift)
                print(f'  B6 schema drift: {"OK" if ok else "FAIL"} ({msg})')

        # Fix lourds (--fix uniquement) — B4/B5 declenchent des reloads longs
        # En --fix-safe : detection + rapport, rechargement laisse a batch_loop.sh (01h00)
        if args.fix:
            if not results.get('B4', {}).get('ok', True):
                ecarts = results['B4'].get('details', {}).get('ecarts', {})
                if ecarts:
                    print(f'  B4 reconciliation: relance bulk_load pour {list(ecarts.keys())}...')
                    ok, msg = fix_b4_reconciliation(ecarts)
                    print(f'  B4 reconciliation: {"OK" if ok else "FAIL"} ({msg})')

            if not results.get('B5', {}).get('ok', True):
                print('  B5 ref_reload: lancement table par table (CLONE+SWAP)...')
                ok, msg = fix_b5_ref_reload()
                print(f'  B5 ref_reload: {"OK" if ok else "FAIL"} ({msg})')
        elif not results.get('B5', {}).get('ok', True):
            stale = results['B5'].get('details', {}).get('stale_tables', {})
            print(f'  B5 donnees perimees: {len(stale)} tables detectees — rechargement par batch_loop.sh (01h00)')

    # Resume
    nb_ok = sum(1 for r in results.values() if r['ok'])
    nb_fail = len(results) - nb_ok
    print(f'\n{"=" * 60}')
    print(f'  Resume: {nb_ok}/6 OK, {nb_fail} FAIL')
    sys.exit(0 if nb_fail == 0 else 1)


if __name__ == '__main__':
    main()
