"""Injection de données test dans MySQL RDS pour valider le workflow CDC.

Usage :
    python3 scripts/cdc_test_injection.py --insert
    python3 scripts/cdc_test_injection.py --delete
    python3 scripts/cdc_test_injection.py --show

Les IDs fictifs (PHA_ID=99999, PRD_ID=888888, COM_GROI=999999999)
ne doivent pas entrer en collision avec la donnée réelle. Le mode --insert
DELETE les éventuels résidus avant insertion pour rester idempotent.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Dict, List, Tuple

import mysql.connector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TEST_PHA_ID = 99999
TEST_COM_GROI = 999999999
TEST_PRD_ID_A = 888888
TEST_PRD_ID_B = 888889
TEST_FAC_ID = 999999
TEST_FAC_TI = 999

TABLES = ["COMMANDES", "FACTURES", "ORDERS", "MODSTOCK"]


def _connect() -> mysql.connector.MySQLConnection:
    """Ouvre la connexion MySQL RDS avec les credentials du conteneur."""
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ.get("MYSQL_DATABASE", "winstat"),
        connection_timeout=30,
    )


def _count_test_rows(cur: mysql.connector.cursor.MySQLCursor) -> Dict[str, int]:
    """Compte les lignes de test (PHA_ID=99999) dans chacune des 4 tables."""
    counts: Dict[str, int] = {}
    for table in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE PHA_ID = %s", (TEST_PHA_ID,))
        counts[table] = cur.fetchone()[0]
    return counts


def _delete_test_rows(cur: mysql.connector.cursor.MySQLCursor) -> int:
    """Supprime toutes les lignes de test. Retourne le total effacé."""
    total = 0
    for table in TABLES:
        cur.execute(f"DELETE FROM {table} WHERE PHA_ID = %s", (TEST_PHA_ID,))
        total += cur.rowcount
        logger.info("DELETE %s : %d ligne(s)", table, cur.rowcount)
    return total


def _insert_commandes(cur: mysql.connector.cursor.MySQLCursor) -> int:
    """Insère 2 lignes COMMANDES (2 produits sur la même commande)."""
    rows: List[Tuple] = [
        (TEST_PHA_ID, TEST_COM_GROI, TEST_PRD_ID_A, 1, "TESTFOU_CDC001", 10, 12.50, 5.00),
        (TEST_PHA_ID, TEST_COM_GROI, TEST_PRD_ID_B, 1, "TESTFOU_CDC001", 5, 8.90, 3.50),
    ]
    cur.executemany(
        """
        INSERT INTO COMMANDES
            (PHA_ID, COM_GROI, PRD_ID, COM_GROS, COM_DATE,
             FOU_ID, COM_QUANTITE, COM_PAHTNET, COM_TAUXREMISE)
        VALUES (%s, %s, %s, %s, CURDATE(), %s, %s, %s, %s)
        """,
        rows,
    )
    return cur.rowcount


def _insert_factures(cur: mysql.connector.cursor.MySQLCursor) -> int:
    """Insère 1 ligne FACTURES (vente du produit 888888)."""
    cur.execute(
        """
        INSERT INTO FACTURES
            (PHA_ID, FAC_ID, FAC_TI, FAC_BASE, FAC_DATE, PRD_ID,
             FAC_TVA, FAC_QUANTITE, FAC_PAHT, FAC_PVHT, FAC_PVTTC,
             FAC_PRIXPUBLIC, FAC_REMISE, FAC_CODEREMBT,
             FAC_HISTO_NBCLIENT, FAC_PROMO, FAC_RETRO, FAC_LOCATION, FAC_ORDO)
        VALUES
            (%s, %s, %s, 0, NOW(), %s,
             5.50, 2, 12.50, 15.00, 15.82,
             16.00, 0.00, 0,
             1, 0, 0, 0, 0)
        """,
        (TEST_PHA_ID, TEST_FAC_ID, TEST_FAC_TI, TEST_PRD_ID_A),
    )
    return cur.rowcount


def _insert_orders(cur: mysql.connector.cursor.MySQLCursor) -> int:
    """Insère 1 ligne ORDERS (en-tête de vente lié à la FACTURE)."""
    cur.execute(
        """
        INSERT INTO ORDERS
            (PHA_ID, FAC_ID, ORD_DATE, ORD_OPERATEUR,
             ORD_HISTO_NBCLIENT, ORD_BASE, ORD_RETRO, ORD_LOCATION,
             ORD_ORDO, ORD_AVR, ORD_ANN)
        VALUES
            (%s, %s, NOW(), 'TEST_OPERATEUR_CDC', 1, 0, 0, 0, 0, 0, 0)
        """,
        (TEST_PHA_ID, TEST_FAC_ID),
    )
    return cur.rowcount


def _insert_modstock(cur: mysql.connector.cursor.MySQLCursor) -> int:
    """Insère 1 ligne MODSTOCK (mouvement de stock lié au produit vendu)."""
    cur.execute(
        """
        INSERT INTO MODSTOCK
            (PHA_ID, MOD_DATE, PRD_ID, MOD_TIMESTAMP, MOD_DELTA, MOD_TI,
             MOD_STOCK, MOD_FACTURE, MOD_COMMANDE, MOD_OPERATION, MOD_POSTE)
        VALUES
            (%s, NOW(), %s, UNIX_TIMESTAMP(), -2, %s,
             8, %s, %s, 1, 'TEST_POSTE_CDC')
        """,
        (
            TEST_PHA_ID,
            TEST_PRD_ID_A,
            TEST_COM_GROI,
            TEST_FAC_ID,
            TEST_COM_GROI,
        ),
    )
    return cur.rowcount


def action_show() -> None:
    """Affiche l'état courant des lignes de test dans MySQL RDS."""
    conn = _connect()
    try:
        cur = conn.cursor()
        counts = _count_test_rows(cur)
        logger.info("État MySQL RDS (PHA_ID=%d) :", TEST_PHA_ID)
        for table, count in counts.items():
            logger.info("  %-10s : %d ligne(s)", table, count)
        cur.close()
    finally:
        conn.close()


def action_insert() -> None:
    """Nettoie puis insère 5 lignes de test réparties sur les 4 tables."""
    conn = _connect()
    try:
        cur = conn.cursor()

        logger.info("Nettoyage préalable (idempotence)")
        _delete_test_rows(cur)

        logger.info("Insertion des lignes de test")
        n_com = _insert_commandes(cur)
        logger.info("INSERT COMMANDES : %d ligne(s)", n_com)
        n_fac = _insert_factures(cur)
        logger.info("INSERT FACTURES  : %d ligne(s)", n_fac)
        n_ord = _insert_orders(cur)
        logger.info("INSERT ORDERS    : %d ligne(s)", n_ord)
        n_mod = _insert_modstock(cur)
        logger.info("INSERT MODSTOCK  : %d ligne(s)", n_mod)

        conn.commit()
        total = n_com + n_fac + n_ord + n_mod
        logger.info("COMMIT OK — %d ligne(s) injectées au total", total)
        logger.info("Debezium devrait publier %d events sur winstat_rds.winstat.*", total)

        cur.close()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"[insert] échec injection : {e}") from e
    finally:
        conn.close()


def action_delete() -> None:
    """Supprime les lignes de test (utilisé pour le 2ème cycle de validation)."""
    conn = _connect()
    try:
        cur = conn.cursor()
        logger.info("Suppression des lignes de test")
        total = _delete_test_rows(cur)
        conn.commit()
        logger.info("COMMIT OK — %d ligne(s) supprimées", total)
        logger.info("Debezium devrait publier %d events 'd' (delete)", total)
        cur.close()
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"[delete] échec suppression : {e}") from e
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--insert", action="store_true", help="Injecte les 5 lignes de test")
    group.add_argument("--delete", action="store_true", help="Supprime les lignes de test")
    group.add_argument("--show", action="store_true", help="Affiche l'état courant")
    args = parser.parse_args()

    if args.insert:
        action_insert()
    elif args.delete:
        action_delete()
    else:
        action_show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
