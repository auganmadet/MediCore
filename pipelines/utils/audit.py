"""Utilitaire audit : log pipeline runs et steps dans MEDICORE_PROD.AUDIT.

Chaque fonction ouvre/ferme sa propre connexion (~1s par appel, ~7 appels par batch).
Encapsulé dans try/except — l'audit ne doit jamais casser le pipeline.
"""

import os
import logging
from datetime import datetime
from typing import Optional

import snowflake.connector

logger = logging.getLogger(__name__)


def _get_audit_conn() -> snowflake.connector.SnowflakeConnection:
    """Connexion Snowflake vers le schéma AUDIT."""
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDIcore'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDIcore_WH'),
        schema='AUDIT',
    )


def log_run_start(run_id: str, env: str, triggered_by: str = 'batch_loop') -> None:
    """Insère une nouvelle ligne PIPELINE_RUNS au début d'une itération batch."""
    try:
        conn = _get_audit_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO PIPELINE_RUNS (RUN_ID, RUN_START, STATUS, ENV, TRIGGERED_BY) "
            "VALUES (%s, %s, 'RUNNING', %s, %s)",
            (run_id, datetime.utcnow().isoformat(), env, triggered_by),
        )
        cursor.close()
        conn.close()
        logger.info(f"Audit run start: {run_id}")
    except Exception as exc:
        logger.warning(f"Audit log_run_start échoué (non bloquant): {exc}")


def log_run_end(run_id: str, status: str) -> None:
    """Met à jour PIPELINE_RUNS avec le statut final et l'heure de fin."""
    try:
        conn = _get_audit_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE PIPELINE_RUNS SET STATUS = %s, RUN_END = %s WHERE RUN_ID = %s",
            (status, datetime.utcnow().isoformat(), run_id),
        )
        cursor.close()
        conn.close()
        logger.info(f"Audit run end: {run_id} -> {status}")
    except Exception as exc:
        logger.warning(f"Audit log_run_end échoué (non bloquant): {exc}")


def log_step_start(run_id: str, step_name: str) -> None:
    """Insère une nouvelle ligne PIPELINE_STEP_RUNS au début d'une phase."""
    try:
        conn = _get_audit_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO PIPELINE_STEP_RUNS (RUN_ID, STEP_NAME, STEP_START, STATUS) "
            "VALUES (%s, %s, %s, 'RUNNING')",
            (run_id, step_name, datetime.utcnow().isoformat()),
        )
        cursor.close()
        conn.close()
    except Exception as exc:
        logger.warning(f"Audit log_step_start échoué (non bloquant): {exc}")


def log_step_end(
    run_id: str,
    step_name: str,
    status: str,
    rows_affected: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Met à jour PIPELINE_STEP_RUNS avec le statut final, rows et erreur."""
    try:
        conn = _get_audit_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE PIPELINE_STEP_RUNS "
            "SET STATUS = %s, STEP_END = %s, ROWS_AFFECTED = %s, ERROR_MESSAGE = %s "
            "WHERE RUN_ID = %s AND STEP_NAME = %s",
            (
                status,
                datetime.utcnow().isoformat(),
                rows_affected,
                str(error)[:4000] if error else None,
                run_id,
                step_name,
            ),
        )
        cursor.close()
        conn.close()
    except Exception as exc:
        logger.warning(f"Audit log_step_end échoué (non bloquant): {exc}")
