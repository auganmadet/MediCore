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
import os
import re
import signal
import sys
import time
import logging
from datetime import datetime

# Import des fonctions existantes de bulk_load.py (pas de duplication)
from bulk_load import (
    get_mysql_conn, get_snowflake_conn, bulk_load_table,
    TABLE_MAPPING, CDC_TABLES, ensure_stage, ensure_export_dir,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cles primaires par table (extraites de DDL_TABLES.sql)
PRIMARY_KEYS = {
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
    # RAW_PHARMACIES_ERREUR : id est un FK, pas une PK unique (plusieurs erreurs par pharmacie)
    # Pas de check doublons sur cette table
}


ALL_SF_TABLES = set(TABLE_MAPPING.values())
# Mapping inverse : RAW_TABLE -> mysql_table
SF_TO_MYSQL = {v: k for k, v in TABLE_MAPPING.items()}


# =============================================================================
# Phase 1 : Diagnostic (lecture seule)
# =============================================================================

def check_zombie_processes():
    """Detecte les processus bulk_load.py encore actifs via /proc (ps absent du container)."""
    zombies = []
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


def find_all_logs():
    """Trouve tous les fichiers log du bulk load, tries par date (plus recent en premier)."""
    log_patterns = ['/tmp/bulk_reload_*.log', '/tmp/bulk_remaining.log', '/tmp/bulk_recovery.log']
    all_logs = []
    for pattern in log_patterns:
        all_logs.extend(glob.glob(pattern))

    if not all_logs:
        return []

    all_logs.sort(key=os.path.getmtime, reverse=True)
    return all_logs


def parse_log(log_file):
    """Parse le log bulk load pour extraire les tables OK, en erreur, et non demarrees."""
    tables_ok = {}     # sf_table -> {'rows': int, 'time': float, 'files': int}
    tables_error = {}  # mysql_table -> error_message
    tables_started = set()

    with open(log_file, 'r') as f:
        content = f.read()

    # Tables OK : "RAW_COMMANDES: 40,888,493 rows en 522.5s (82 fichiers Parquet)"
    for match in re.finditer(r'(RAW_\w+): ([\d,]+) rows en ([\d.]+)s \((\d+) fichiers', content):
        sf_table = match.group(1)
        rows = int(match.group(2).replace(',', ''))
        elapsed = float(match.group(3))
        files = int(match.group(4))
        tables_ok[sf_table] = {'rows': rows, 'time': elapsed, 'files': files}

    # Tables en erreur : "ERREUR MEDIPRIX_FACTURES: 2013 (HY000): Lost connection"
    for match in re.finditer(r'ERREUR (\w+): (.+)', content):
        mysql_table = match.group(1)
        error_msg = match.group(2).strip()
        tables_error[mysql_table] = error_msg

    # Tables demarrees : "Loading FACTURES -> RAW_FACTURES..."
    for match in re.finditer(r'Loading (\w+) -> (RAW_\w+)', content):
        tables_started.add(match.group(1))

    # Tables non demarrees
    tables_not_started = []
    for mysql_table in TABLE_MAPPING:
        sf_table = TABLE_MAPPING[mysql_table]
        if mysql_table not in tables_started and sf_table not in tables_ok:
            tables_not_started.append(mysql_table)

    return tables_ok, tables_error, tables_not_started


def check_snowflake_tables(sf_conn):
    """Verifie l'etat de chaque table RAW dans Snowflake."""
    results = {}
    cursor = sf_conn.cursor()
    current_year = datetime.now().year

    for sf_table in sorted(ALL_SF_TABLES):
        info = {'rows': 0, 'distinct': 0, 'ts_ok': True, 'issues': []}

        try:
            # Count total
            cursor.execute(f"SELECT COUNT(*) FROM {sf_table}")
            info['rows'] = cursor.fetchone()[0]

            if info['rows'] == 0:
                info['issues'].append('VIDE')
                results[sf_table] = info
                continue

            # Check doublons via cle primaire
            # COUNT(DISTINCT (col1,col2)) invalide en Snowflake → sous-requete
            pk_cols = PRIMARY_KEYS.get(sf_table)
            if pk_cols:
                pk_expr = ', '.join(pk_cols)
                cursor.execute(f"SELECT COUNT(*) FROM (SELECT DISTINCT {pk_expr} FROM {sf_table})")
                info['distinct'] = cursor.fetchone()[0]
                if info['distinct'] < info['rows']:
                    info['issues'].append(f"DOUBLONS ({info['rows']:,} rows vs {info['distinct']:,} distincts)")

            # Check timestamps
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

        except Exception as e:
            info['issues'].append(f"ERREUR SQL: {e}")

        results[sf_table] = info

    cursor.close()
    return results


def run_diagnostic(sf_conn):
    """Execute le diagnostic complet et retourne les tables a recharger."""
    print("\n" + "=" * 70)
    print("  DIAGNOSTIC BULK LOAD")
    print("=" * 70)

    # 1. Processus zombies
    print("\n--- PROCESSUS ---")
    zombies = check_zombie_processes()
    if zombies:
        for z in zombies:
            print(f"  [ZOMBIE] PID {z['pid']}: {z['cmdline']}")
    else:
        print("  [OK] Aucun processus bulk_load.py actif")

    # 2. Analyse des logs (tous les fichiers, pas juste le dernier)
    print("\n--- LOGS ---")
    log_files = find_all_logs()
    tables_ok = {}
    tables_error = {}

    if log_files:
        for log_file in log_files:
            mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
            ok, err, _ = parse_log(log_file)
            print(f"  {log_file} ({mtime:%Y-%m-%d %H:%M}): {len(ok)} OK, {len(err)} erreurs")
            # Fusionner (le plus recent gagne en cas de conflit)
            for sf_table, info in ok.items():
                if sf_table not in tables_ok:
                    tables_ok[sf_table] = info
            for mysql_table, msg in err.items():
                sf_table = TABLE_MAPPING.get(mysql_table)
                # Ignorer l'erreur si la table a ete rechargee avec succes dans un autre log
                if sf_table and sf_table not in tables_ok:
                    tables_error[mysql_table] = msg

        # Tables non demarrees dans aucun log
        tables_not_started = []
        all_ok_sf = set(tables_ok.keys())
        all_err_mysql = set(tables_error.keys())
        for mysql_table in TABLE_MAPPING:
            sf_table = TABLE_MAPPING[mysql_table]
            if sf_table not in all_ok_sf and mysql_table not in all_err_mysql:
                tables_not_started.append(mysql_table)

        if tables_ok:
            print(f"  [OK] {len(tables_ok)} tables chargees avec succes (tous logs confondus)")
        if tables_error:
            for t, err in tables_error.items():
                print(f"  [ERREUR] {t}: {err}")
        if tables_not_started:
            print(f"  [MANQUE] {len(tables_not_started)} tables non demarrees: {', '.join(tables_not_started)}")
    else:
        print("  [INFO] Aucun log trouve dans /tmp/")
        tables_not_started = list(TABLE_MAPPING.keys())

    # 3. Verification Snowflake
    print("\n--- SNOWFLAKE ---")
    sf_results = check_snowflake_tables(sf_conn)
    tables_to_reload = set()

    for sf_table in sorted(sf_results.keys()):
        info = sf_results[sf_table]
        if info['issues']:
            status = ', '.join(info['issues'])
            print(f"  [PROBLEME] {sf_table:30s} {info['rows']:>12,} rows | {status}")
            tables_to_reload.add(sf_table)
        else:
            print(f"  [OK]       {sf_table:30s} {info['rows']:>12,} rows")

    # Ajouter les tables en erreur/non demarrees du log, seulement si Snowflake confirme un probleme
    for mysql_table in list(tables_error.keys()) + tables_not_started:
        sf_table = TABLE_MAPPING.get(mysql_table)
        if sf_table:
            info = sf_results.get(sf_table, {})
            # Si Snowflake montre la table OK (rows > 0, pas de doublons), ne pas recharger
            if info.get('issues') or info.get('rows', 0) == 0:
                tables_to_reload.add(sf_table)

    # Resume
    print("\n--- RESUME ---")
    if not tables_to_reload and not zombies:
        print("  [OK] Toutes les 18 tables sont correctement chargees")
        return zombies, tables_to_reload

    if zombies:
        print(f"  {len(zombies)} processus zombie(s) a tuer")
    if tables_to_reload:
        print(f"  {len(tables_to_reload)} table(s) a recharger:")
        for sf_t in sorted(tables_to_reload):
            mysql_t = SF_TO_MYSQL.get(sf_t, '?')
            reason = ', '.join(sf_results.get(sf_t, {}).get('issues', ['non charge']))
            print(f"    - {sf_t} ({mysql_t}): {reason}")
        print(f"\n  -> Lancer avec --fix pour corriger automatiquement")

    return zombies, tables_to_reload


# =============================================================================
# Phase 2 : Correction (--fix)
# =============================================================================

def kill_zombies(zombies):
    """Tue les processus bulk_load.py zombies."""
    for z in zombies:
        pid = z['pid']
        print(f"  Envoi SIGTERM au PID {pid}...")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            print(f"  PID {pid} deja termine")
            continue

        # Attendre 5s puis SIGKILL si toujours actif
        time.sleep(5)
        try:
            os.kill(pid, 0)  # Test si le process existe encore
            print(f"  PID {pid} toujours actif, envoi SIGKILL...")
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            print(f"  PID {pid} termine")


def reload_tables(sf_conn, tables_to_reload, chunk_size=500000):
    """Recharge les tables en echec via bulk_load_table()."""
    ensure_stage(sf_conn)
    ensure_export_dir()

    success = []
    errors = []

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
        except Exception as e:
            logger.error(f"ERREUR recovery {mysql_table}: {e}")
            errors.append(sf_table)
        finally:
            if mysql_conn:
                mysql_conn.close()

    return success, errors


def run_fix(sf_conn, zombies, tables_to_reload):
    """Execute les corrections automatiques."""
    print("\n" + "=" * 70)
    print("  CORRECTION AUTOMATIQUE")
    print("=" * 70)

    # 2.1 Kill zombies
    if zombies:
        print("\n--- KILL PROCESSUS ZOMBIES ---")
        kill_zombies(zombies)
        # Attendre que les processus liberent leurs ressources
        time.sleep(3)

    # 2.2 Recharger les tables
    if tables_to_reload:
        print(f"\n--- RECHARGEMENT DE {len(tables_to_reload)} TABLE(S) ---")
        success, errors = reload_tables(sf_conn, tables_to_reload)

        # 2.3 Verification post-fix
        print("\n--- VERIFICATION POST-FIX ---")
        sf_results = check_snowflake_tables(sf_conn)
        still_broken = []
        for sf_table in sorted(tables_to_reload):
            info = sf_results.get(sf_table, {})
            if info.get('issues'):
                status = ', '.join(info['issues'])
                print(f"  [ECHEC]  {sf_table:30s} {status}")
                still_broken.append(sf_table)
            else:
                print(f"  [OK]     {sf_table:30s} {info.get('rows', 0):>12,} rows")

        # Resume final
        print("\n--- RESUME CORRECTION ---")
        if success:
            total = sum(r for _, r in success)
            print(f"  {len(success)} table(s) rechargee(s) avec succes ({total:,} rows)")
        if errors:
            print(f"  {len(errors)} table(s) en echec: {', '.join(errors)}")
        if still_broken:
            print(f"  {len(still_broken)} table(s) toujours en erreur apres correction")
            sys.exit(1)
        elif not errors:
            print("  Toutes les corrections appliquees avec succes")
    else:
        print("\n  Rien a corriger")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Diagnostic et recovery automatique du bulk load'
    )
    parser.add_argument('--fix', action='store_true',
                        help='Corriger automatiquement les problemes detectes')
    parser.add_argument('--chunk-size', type=int, default=500000,
                        help='Lignes par fichier Parquet pour le rechargement (defaut: 500000)')
    args = parser.parse_args()

    # Connexion Snowflake pour le diagnostic
    sf_conn = get_snowflake_conn()

    try:
        # Phase 1 : Diagnostic
        zombies, tables_to_reload = run_diagnostic(sf_conn)

        # Phase 2 : Correction (si --fix)
        if args.fix:
            if not zombies and not tables_to_reload:
                print("\n  Aucune correction necessaire")
            else:
                run_fix(sf_conn, zombies, tables_to_reload)
    finally:
        sf_conn.close()


if __name__ == '__main__':
    main()
