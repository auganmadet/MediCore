#!/usr/bin/env python3
"""
Diagnostic et recovery automatique du bulk load MySQL -> Snowflake.

Deux modes :
  python diagnose_recover.py           # Diagnostic seul (lecture seule)
  python diagnose_recover.py --fix     # Diagnostic + correction automatique

Detecte et corrige :
  - Processus zombies (bulk_load.py encore actif apres crash)
  - Tables vides (TRUNCATE sans COPY INTO)
  - Doublons (processus zombie + COPY INTO concurrent)
  - Timestamps invalides (YEAR != annee courante)
  - Tables non chargees (erreur reseau, DNS, OOM)
"""

import argparse
import glob
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

import snowflake.connector

from bulk_load import (
    get_mysql_conn, get_snowflake_conn, bulk_load_table,
    TABLE_MAPPING, ensure_stage, ensure_export_dir,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cles primaires par table (extraites de DDL_TABLES.sql)
PRIMARY_KEYS: Dict[str, List[str]] = {
    'RAW_COMMANDES': ['PHA_ID', 'COM_GROI', 'PRD_ID'],
    'RAW_FACTURES': ['PHA_ID', 'FAC_ID', 'FAC_TI'],
    'RAW_ORDERS': ['PHA_ID', 'FAC_ID'],
    'RAW_MODSTOCK': ['PHA_ID', 'MOD_DATE', 'PRD_ID', 'MOD_TIMESTAMP'],
    'RAW_DAYBYDAY': ['PHA_ID', 'DBD_DATE', 'PRD_ID'],
    'RAW_EAN13': ['PHA_ID', 'EAN_13', 'PRD_ID'],
    'RAW_FOURNISSEURS': ['PHA_ID', 'FOU_ID'],
    'RAW_HISTORY': ['PHA_ID', '"Date"'],
    'RAW_LOG': ['PHA_ID'],
    'RAW_LPPR': ['PHA_ID', 'PRD_ID', 'LPP_INDEX', 'LPP_CODE'],
    'RAW_MANQHISTORY': ['PHA_ID', 'MNQ_DATE', 'PRD_ID', 'FAC_ID'],
    'RAW_MEDIPRIX_FACTURES': ['PHA_ID', 'FAC_ID', 'FAC_TI'],
    'RAW_PHARMACIE': ['PHA_ID'],
    'RAW_PRODUITS': ['PHA_ID', 'PRD_ID'],
    'RAW_PRODUITS_NEGATIFS': ['PRD_ID'],
    'RAW_STOCKHISTORY': ['PHA_ID', 'PRD_ID', 'STH_DATE'],
    'RAW_PHARMACIES': ['ID'],
    # RAW_PHARMACIES_ERREUR : id est un FK, pas une PK unique
}

ALL_SF_TABLES: Set[str] = set(TABLE_MAPPING.values())
SF_TO_MYSQL: Dict[str, str] = {v: k for k, v in TABLE_MAPPING.items()}


# =============================================================================
# Phase 1 : Diagnostic (lecture seule)
# =============================================================================

def check_zombie_processes() -> List[Dict[str, Any]]:
    """Detecte les processus bulk_load.py actifs via /proc.

    Returns:
        Liste de dicts avec pid et cmdline pour chaque zombie detecte.
    """
    zombies: List[Dict[str, Any]] = []
    my_pid = os.getpid()
    my_ppid = os.getppid()

    for pid_dir in glob.glob('/proc/[0-9]*'):
        pid = int(os.path.basename(pid_dir))
        if pid in (my_pid, my_ppid):
            continue
        try:
            with open(os.path.join(pid_dir, 'cmdline'), 'rb') as f:
                cmdline = f.read().decode('utf-8', errors='replace').replace('\x00', ' ').strip()
            if 'bulk_load.py' in cmdline and 'diagnose_recover' not in cmdline:
                zombies.append({'pid': pid, 'cmdline': cmdline})
        except (FileNotFoundError, PermissionError):
            continue

    return zombies


def find_all_logs() -> List[str]:
    """Trouve les fichiers log du bulk load, tries par date decroissante.

    Returns:
        Liste de chemins de fichiers log, du plus recent au plus ancien.
    """
    log_patterns = ['/tmp/bulk_reload_*.log', '/tmp/bulk_remaining.log', '/tmp/bulk_recovery.log']
    all_logs: List[str] = []
    for pattern in log_patterns:
        all_logs.extend(glob.glob(pattern))

    if not all_logs:
        return []

    all_logs.sort(key=os.path.getmtime, reverse=True)
    return all_logs


def parse_log(log_file: str) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], List[str]]:
    """Parse le log bulk load pour extraire les tables OK, erreur et non demarrees.

    Args:
        log_file: Chemin vers le fichier log a analyser.

    Returns:
        Tuple (tables_ok, tables_error, tables_not_started).
    """
    tables_ok: Dict[str, Dict[str, Any]] = {}
    tables_error: Dict[str, str] = {}
    tables_started: Set[str] = set()

    with open(log_file, 'r') as f:
        content = f.read()

    for match in re.finditer(r'(RAW_\w+): ([\d,]+) rows en ([\d.]+)s \((\d+) fichiers', content):
        sf_table = match.group(1)
        rows = int(match.group(2).replace(',', ''))
        elapsed = float(match.group(3))
        files = int(match.group(4))
        tables_ok[sf_table] = {'rows': rows, 'time': elapsed, 'files': files}

    for match in re.finditer(r'ERREUR (\w+): (.+)', content):
        mysql_table = match.group(1)
        error_msg = match.group(2).strip()
        tables_error[mysql_table] = error_msg

    for match in re.finditer(r'Loading (\w+) -> (RAW_\w+)', content):
        tables_started.add(match.group(1))

    tables_not_started: List[str] = []
    for mysql_table in TABLE_MAPPING:
        sf_table = TABLE_MAPPING[mysql_table]
        if mysql_table not in tables_started and sf_table not in tables_ok:
            tables_not_started.append(mysql_table)

    return tables_ok, tables_error, tables_not_started


def check_table_row_count(cursor: Any, sf_table: str, info: Dict[str, Any]) -> None:
    """Verifie le nombre de lignes et les doublons pour une table.

    Args:
        cursor: Curseur Snowflake actif.
        sf_table: Nom de la table Snowflake.
        info: Dict a enrichir avec rows, distinct et issues.
    """
    cursor.execute(f"SELECT COUNT(*) FROM {sf_table}")
    info['rows'] = cursor.fetchone()[0]

    if info['rows'] == 0:
        info['issues'].append('VIDE')
        return

    pk_cols = PRIMARY_KEYS.get(sf_table)
    if pk_cols:
        pk_expr = ', '.join(pk_cols)
        cursor.execute(f"SELECT COUNT(*) FROM (SELECT DISTINCT {pk_expr} FROM {sf_table})")
        info['distinct'] = cursor.fetchone()[0]
        if info['distinct'] < info['rows']:
            info['issues'].append(f"DOUBLONS ({info['rows']:,} rows vs {info['distinct']:,} distincts)")


def check_table_timestamps(cursor: Any, sf_table: str, info: Dict[str, Any]) -> None:
    """Verifie la coherence des timestamps CDC pour une table.

    Args:
        cursor: Curseur Snowflake actif.
        sf_table: Nom de la table Snowflake.
        info: Dict a enrichir avec ts_ok et issues.
    """
    current_year = datetime.now().year
    cursor.execute(f"""
        SELECT MIN(YEAR(CDC_TIMESTAMP)), MAX(YEAR(CDC_TIMESTAMP))
        FROM {sf_table}
        WHERE CDC_TIMESTAMP IS NOT NULL
    """)
    row = cursor.fetchone()
    if row and row[0] is not None:
        min_year, max_year = row[0], row[1]
        if min_year != current_year or max_year != current_year:
            info['ts_ok'] = False
            info['issues'].append(f"TIMESTAMPS (year {min_year}-{max_year}, attendu {current_year})")


def check_snowflake_tables(sf_conn: Any) -> Dict[str, Dict[str, Any]]:
    """Verifie l'etat de chaque table RAW dans Snowflake.

    Args:
        sf_conn: Connexion Snowflake active.

    Returns:
        Dict table_name -> {rows, distinct, ts_ok, issues}.
    """
    results: Dict[str, Dict[str, Any]] = {}
    cursor = sf_conn.cursor()

    for sf_table in sorted(ALL_SF_TABLES):
        info: Dict[str, Any] = {'rows': 0, 'distinct': 0, 'ts_ok': True, 'issues': []}
        try:
            check_table_row_count(cursor, sf_table, info)
            if info['rows'] > 0:
                check_table_timestamps(cursor, sf_table, info)
        except snowflake.connector.errors.ProgrammingError as e:
            info['issues'].append(f"ERREUR SQL: {e}")
        results[sf_table] = info

    cursor.close()
    return results


def _diagnose_processes() -> List[Dict[str, Any]]:
    """Sous-etape diagnostic : detecte les processus zombies."""
    logger.info("--- PROCESSUS ---")
    zombies = check_zombie_processes()
    if zombies:
        for z in zombies:
            logger.warning(f"  [ZOMBIE] PID {z['pid']}: {z['cmdline']}")
    else:
        logger.info("  [OK] Aucun processus bulk_load.py actif")
    return zombies


def _diagnose_logs() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str], List[str]]:
    """Sous-etape diagnostic : analyse les logs du bulk load."""
    logger.info("--- LOGS ---")
    log_files = find_all_logs()
    tables_ok: Dict[str, Dict[str, Any]] = {}
    tables_error: Dict[str, str] = {}
    tables_not_started: List[str] = []

    if not log_files:
        logger.info("  [INFO] Aucun log trouve dans /tmp/")
        return tables_ok, tables_error, list(TABLE_MAPPING.keys())

    for log_file in log_files:
        mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
        ok, err, _ = parse_log(log_file)
        logger.info(f"  {log_file} ({mtime:%Y-%m-%d %H:%M}): {len(ok)} OK, {len(err)} erreurs")
        for sf_table, info in ok.items():
            if sf_table not in tables_ok:
                tables_ok[sf_table] = info
        for mysql_table, msg in err.items():
            sf_table = TABLE_MAPPING.get(mysql_table)
            if sf_table and sf_table not in tables_ok:
                tables_error[mysql_table] = msg

    all_ok_sf = set(tables_ok.keys())
    all_err_mysql = set(tables_error.keys())
    for mysql_table in TABLE_MAPPING:
        sf_table = TABLE_MAPPING[mysql_table]
        if sf_table not in all_ok_sf and mysql_table not in all_err_mysql:
            tables_not_started.append(mysql_table)

    if tables_ok:
        logger.info(f"  [OK] {len(tables_ok)} tables chargees avec succes (tous logs confondus)")
    if tables_error:
        for t, err in tables_error.items():
            logger.warning(f"  [ERREUR] {t}: {err}")
    if tables_not_started:
        logger.info(f"  [MANQUE] {len(tables_not_started)} tables non demarrees: {', '.join(tables_not_started)}")

    return tables_ok, tables_error, tables_not_started


def _diagnose_snowflake(sf_conn: Any, tables_error: Dict[str, str], tables_not_started: List[str]) -> Set[str]:
    """Sous-etape diagnostic : verifie les tables Snowflake et identifie celles a recharger.

    Args:
        sf_conn: Connexion Snowflake active.
        tables_error: Tables en erreur dans les logs.
        tables_not_started: Tables non demarrees dans les logs.

    Returns:
        Ensemble des tables Snowflake a recharger.
    """
    logger.info("--- SNOWFLAKE ---")
    sf_results = check_snowflake_tables(sf_conn)
    tables_to_reload: Set[str] = set()

    for sf_table in sorted(sf_results.keys()):
        info = sf_results[sf_table]
        if info['issues']:
            status = ', '.join(info['issues'])
            logger.warning(f"  [PROBLEME] {sf_table:30s} {info['rows']:>12,} rows | {status}")
            tables_to_reload.add(sf_table)
        else:
            logger.info(f"  [OK]       {sf_table:30s} {info['rows']:>12,} rows")

    for mysql_table in list(tables_error.keys()) + tables_not_started:
        sf_table = TABLE_MAPPING.get(mysql_table)
        if sf_table:
            info = sf_results.get(sf_table, {})
            if info.get('issues') or info.get('rows', 0) == 0:
                tables_to_reload.add(sf_table)

    return tables_to_reload


def run_diagnostic(sf_conn: Any) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Execute le diagnostic complet et retourne les elements a corriger.

    Args:
        sf_conn: Connexion Snowflake active.

    Returns:
        Tuple (zombies, tables_to_reload).
    """
    logger.info("=" * 70)
    logger.info("  DIAGNOSTIC BULK LOAD")
    logger.info("=" * 70)

    zombies = _diagnose_processes()
    _, tables_error, tables_not_started = _diagnose_logs()
    tables_to_reload = _diagnose_snowflake(sf_conn, tables_error, tables_not_started)

    logger.info("--- RESUME ---")
    if not tables_to_reload and not zombies:
        logger.info("  [OK] Toutes les 18 tables sont correctement chargees")
        return zombies, tables_to_reload

    if zombies:
        logger.warning(f"  {len(zombies)} processus zombie(s) a tuer")
    if tables_to_reload:
        logger.info(f"  {len(tables_to_reload)} table(s) a recharger:")
        for sf_t in sorted(tables_to_reload):
            mysql_t = SF_TO_MYSQL.get(sf_t, '?')
            logger.info(f"    - {sf_t} ({mysql_t})")
        logger.info("  -> Lancer avec --fix pour corriger automatiquement")

    return zombies, tables_to_reload


# =============================================================================
# Phase 2 : Correction (--fix)
# =============================================================================

def kill_zombies(zombies: List[Dict[str, Any]]) -> None:
    """Tue les processus bulk_load.py zombies via SIGTERM puis SIGKILL.

    Args:
        zombies: Liste de dicts avec pid et cmdline.
    """
    for z in zombies:
        pid = z['pid']
        logger.info(f"  Envoi SIGTERM au PID {pid}...")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            logger.info(f"  PID {pid} deja termine")
            continue

        time.sleep(5)
        try:
            os.kill(pid, 0)
            logger.warning(f"  PID {pid} toujours actif, envoi SIGKILL...")
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            logger.info(f"  PID {pid} termine")


def reload_tables(sf_conn: Any, tables_to_reload: Set[str], chunk_size: int = 500000) -> Tuple[List[Tuple[str, int]], List[str]]:
    """Recharge les tables en echec via bulk_load_table().

    Args:
        sf_conn: Connexion Snowflake active.
        tables_to_reload: Ensemble des tables Snowflake a recharger.
        chunk_size: Nombre de lignes par fichier Parquet.

    Returns:
        Tuple (success_list, error_list).
    """
    ensure_stage(sf_conn)
    ensure_export_dir()

    success: List[Tuple[str, int]] = []
    errors: List[str] = []

    for sf_table in sorted(tables_to_reload):
        mysql_table = SF_TO_MYSQL.get(sf_table)
        if not mysql_table:
            logger.warning(f"Pas de mapping MySQL pour {sf_table}")
            errors.append(sf_table)
            continue

        mysql_conn = None
        try:
            mysql_conn = get_mysql_conn()
            rows = bulk_load_table(
                mysql_conn, sf_conn, mysql_table, sf_table,
                chunk_size, truncate=True, force=True
            )
            success.append((sf_table, rows))
        except (RuntimeError, OSError) as e:
            logger.error(f"ERREUR recovery {mysql_table}: {e}")
            errors.append(sf_table)
        finally:
            if mysql_conn:
                mysql_conn.close()

    return success, errors


def run_fix(sf_conn: Any, zombies: List[Dict[str, Any]], tables_to_reload: Set[str]) -> None:
    """Execute les corrections automatiques.

    Args:
        sf_conn: Connexion Snowflake active.
        zombies: Processus zombies a tuer.
        tables_to_reload: Tables a recharger.
    """
    logger.info("=" * 70)
    logger.info("  CORRECTION AUTOMATIQUE")
    logger.info("=" * 70)

    if zombies:
        logger.info("--- KILL PROCESSUS ZOMBIES ---")
        kill_zombies(zombies)
        time.sleep(3)

    if not tables_to_reload:
        logger.info("  Rien a corriger")
        return

    logger.info(f"--- RECHARGEMENT DE {len(tables_to_reload)} TABLE(S) ---")
    success, errors = reload_tables(sf_conn, tables_to_reload)

    logger.info("--- VERIFICATION POST-FIX ---")
    sf_results = check_snowflake_tables(sf_conn)
    still_broken: List[str] = []
    for sf_table in sorted(tables_to_reload):
        info = sf_results.get(sf_table, {})
        if info.get('issues'):
            status = ', '.join(info['issues'])
            logger.error(f"  [ECHEC]  {sf_table:30s} {status}")
            still_broken.append(sf_table)
        else:
            logger.info(f"  [OK]     {sf_table:30s} {info.get('rows', 0):>12,} rows")

    logger.info("--- RESUME CORRECTION ---")
    if success:
        total = sum(r for _, r in success)
        logger.info(f"  {len(success)} table(s) rechargee(s) avec succes ({total:,} rows)")
    if errors:
        logger.warning(f"  {len(errors)} table(s) en echec: {', '.join(errors)}")
    if still_broken:
        logger.error(f"  {len(still_broken)} table(s) toujours en erreur apres correction")
        sys.exit(1)
    elif not errors:
        logger.info("  Toutes les corrections appliquees avec succes")


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    """Point d'entree : diagnostic et correction optionnelle du bulk load."""
    parser = argparse.ArgumentParser(
        description='Diagnostic et recovery automatique du bulk load'
    )
    parser.add_argument('--fix', action='store_true',
                        help='Corriger automatiquement les problemes detectes')
    parser.add_argument('--chunk-size', type=int, default=500000,
                        help='Lignes par fichier Parquet pour le rechargement (defaut: 500000)')
    args = parser.parse_args()

    sf_conn = get_snowflake_conn()

    try:
        zombies, tables_to_reload = run_diagnostic(sf_conn)

        if args.fix:
            if not zombies and not tables_to_reload:
                logger.info("  Aucune correction necessaire")
            else:
                run_fix(sf_conn, zombies, tables_to_reload)
    finally:
        sf_conn.close()


if __name__ == '__main__':
    main()
