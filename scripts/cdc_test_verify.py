"""Vérifie la propagation des lignes de test CDC à travers le pipeline.

Usage :
    python3 scripts/cdc_test_verify.py

Attendu après le batch nocturne :
- MySQL RDS : 5 lignes (PHA_ID=99999) réparties sur les 4 tables
- Snowflake RAW : 5 lignes avec cdc_operation='I' + cdc_timestamp récent
- Snowflake STAGING : 5 lignes (pas de filtre delete car cdc_operation='I')
- Snowflake MARTS : présence dans fact_commandes, fact_ventes, fact_stock_mouvements
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List

import mysql.connector
import snowflake.connector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TEST_PHA_ID = 99999
TEST_FAC_ID = 999999
TEST_COM_GROI = 999999999

RAW_CHECKS = [
    ("RAW_COMMANDES", f"PHA_ID = {TEST_PHA_ID}"),
    ("RAW_FACTURES", f"PHA_ID = {TEST_PHA_ID}"),
    ("RAW_ORDERS", f"PHA_ID = {TEST_PHA_ID}"),
    ("RAW_MODSTOCK", f"PHA_ID = {TEST_PHA_ID}"),
]

STAGING_CHECKS = [
    ("STG_COMMANDES", f"PHA_ID = {TEST_PHA_ID}"),
    ("STG_FACTURES", f"PHA_ID = {TEST_PHA_ID}"),
    ("STG_ORDERS", f"PHA_ID = {TEST_PHA_ID}"),
    ("STG_MODSTOCK", f"PHA_ID = {TEST_PHA_ID}"),
]

MARTS_CHECKS = [
    ("FACT_COMMANDES", f"PHA_ID = {TEST_PHA_ID}"),
    ("FACT_VENTES", f"PHA_ID = {TEST_PHA_ID}"),
    ("FACT_STOCK_MOUVEMENTS", f"PHA_ID = {TEST_PHA_ID}"),
]


def _mysql_counts() -> Dict[str, int]:
    """Compte les lignes test dans MySQL RDS."""
    conn = mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ.get("MYSQL_DATABASE", "winstat"),
        connection_timeout=30,
    )
    try:
        cur = conn.cursor()
        counts: Dict[str, int] = {}
        for table in ["COMMANDES", "FACTURES", "ORDERS", "MODSTOCK"]:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE PHA_ID = %s", (TEST_PHA_ID,))
            counts[table] = cur.fetchone()[0]
        cur.close()
        return counts
    finally:
        conn.close()


def _sf_conn() -> snowflake.connector.SnowflakeConnection:
    """Ouvre la connexion Snowflake sur MEDICORE_PROD."""
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE_NAME", "MEDICORE_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "MEDICORE_PROD"),
        role=os.environ.get("SNOWFLAKE_DBT_ROLE_NAME", "MEDICORE_DBT_EXECUTOR"),
    )


def _sf_check_layer(
    cur: snowflake.connector.cursor.SnowflakeCursor,
    schema: str,
    checks: List,
    include_cdc_ts: bool = False,
) -> List[Dict[str, Any]]:
    """Interroge une liste de tables et renvoie count + max(cdc_timestamp) si demandé."""
    results: List[Dict[str, Any]] = []
    for table, where in checks:
        fq = f"{schema}.{table}"
        if include_cdc_ts:
            cur.execute(
                f"SELECT COUNT(*), MAX(CDC_TIMESTAMP), MAX(CDC_OPERATION) FROM {fq} WHERE {where}"
            )
            count, max_ts, max_op = cur.fetchone()
            results.append(
                {"table": table, "count": count, "max_cdc_timestamp": max_ts, "last_op": max_op}
            )
        else:
            cur.execute(f"SELECT COUNT(*) FROM {fq} WHERE {where}")
            count = cur.fetchone()[0]
            results.append({"table": table, "count": count})
    return results


def main() -> int:
    logger.info("=" * 70)
    logger.info("Vérification propagation CDC test (PHA_ID=%d)", TEST_PHA_ID)
    logger.info("=" * 70)

    logger.info("")
    logger.info("[1/4] MySQL RDS (source)")
    mysql_counts = _mysql_counts()
    for table, count in mysql_counts.items():
        logger.info("  %-10s : %d ligne(s)", table, count)

    conn = _sf_conn()
    try:
        cur = conn.cursor()

        logger.info("")
        logger.info("[2/4] Snowflake RAW (après CDC consumer)")
        raw_results = _sf_check_layer(cur, "RAW", RAW_CHECKS, include_cdc_ts=True)
        for r in raw_results:
            logger.info(
                "  %-16s : count=%d last_cdc_ts=%s last_op=%s",
                r["table"],
                r["count"],
                r["max_cdc_timestamp"],
                r["last_op"],
            )

        logger.info("")
        logger.info("[3/4] Snowflake STAGING (après dbt post-reload)")
        stg_results = _sf_check_layer(cur, "STAGING", STAGING_CHECKS)
        for r in stg_results:
            logger.info("  %-16s : count=%d", r["table"], r["count"])

        logger.info("")
        logger.info("[4/4] Snowflake MARTS (après dbt post-reload)")
        marts_results = _sf_check_layer(cur, "MARTS", MARTS_CHECKS)
        for r in marts_results:
            logger.info("  %-22s : count=%d", r["table"], r["count"])

        cur.close()
    finally:
        conn.close()

    logger.info("")
    logger.info("=" * 70)
    logger.info("Verdict attendu après une nuit réussie :")
    logger.info("  - MySQL : COMMANDES=2, FACTURES=1, ORDERS=1, MODSTOCK=1")
    logger.info("  - RAW : mêmes counts + cdc_operation='I' + cdc_timestamp du 2026-04-23")
    logger.info("  - STAGING : mêmes counts")
    logger.info("  - MARTS : fact_commandes=2, fact_ventes>=1, fact_stock_mouvements>=1")
    logger.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
