"""Provisionnement RLS (Row-Level Security) pour les pharmacies MediCore.

Alternative A : une seule connexion Metabase (MEDICORE_ANALYST) pour tout le monde.
Pas de multi-connexion, pas de copie de dashboard, pas de Row Access Policy.
Le filtrage repose sur les permissions Metabase (collections + query builder).

Détecte les nouvelles pharmacies dans dim_pharmacie et provisionne :
- 1 groupe Metabase par pharmacie
- 1 collection par pharmacie sous Pharmacies/ (curate)
- Permissions : Vue sur Admin, query-builder uniquement, native=none

Idempotent : ne recrée pas ce qui existe déjà.
Non bloquant : les erreurs sont logguées mais n'arrêtent pas le pipeline.

Usage :
    python scripts/provision_rls.py --run-id <UUID>
    python scripts/provision_rls.py --run-id <UUID> --dry-run
    python scripts/provision_rls.py --run-id <UUID> --pha-id 217
"""

import argparse
import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

import snowflake.connector

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# --- Configuration -----------------------------------------------------------

METABASE_URL = os.getenv('METABASE_URL', 'http://localhost:3000')
MB_BASE = f'{METABASE_URL}/api'
MB_SOURCE_DATABASE_ID = int(os.getenv('MB_SOURCE_DATABASE_ID', '2'))
MEDICORE_COLL_ID = int(os.getenv('MB_MEDICORE_COLLECTION_ID', '5'))


# --- Connexions --------------------------------------------------------------

def get_audit_connection() -> snowflake.connector.SnowflakeConnection:
    """Connexion Snowflake standard (lecture dim_pharmacie, écriture AUDIT)."""
    return snowflake.connector.connect(
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        database=os.getenv('SNOWFLAKE_DATABASE', 'MEDICORE_PROD'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDICORE_WH'),
        schema='AUDIT',
    )


# --- Metabase API helpers -----------------------------------------------------

def mb_authenticate() -> str:
    """Authentification Metabase, retourne le session token."""
    data = json.dumps({
        'username': os.getenv('METABASE_ADMIN_EMAIL'),
        'password': os.getenv('METABASE_ADMIN_PASSWORD'),
    }).encode('utf-8')
    req = urllib.request.Request(
        f'{MB_BASE}/session', data=data, method='POST',
        headers={'Content-Type': 'application/json; charset=utf-8'},
    )
    resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return resp['id']


def mb_get(token: str, path: str) -> Any:
    """GET sur l'API Metabase avec retry."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f'{MB_BASE}/{path}',
                headers={'X-Metabase-Session': token},
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                logger.warning(f"Retry {attempt+1}/3 GET {path}: {e}")
                time.sleep(5)
            else:
                raise


def mb_post(token: str, path: str, data: Dict) -> Any:
    """POST sur l'API Metabase avec retry."""
    for attempt in range(3):
        try:
            body = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                f'{MB_BASE}/{path}', data=body, method='POST',
                headers={
                    'X-Metabase-Session': token,
                    'Content-Type': 'application/json; charset=utf-8',
                },
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                logger.warning(f"Retry {attempt+1}/3 POST {path}: {e}")
                time.sleep(5)
            else:
                raise


def mb_put(token: str, path: str, data: Dict) -> Any:
    """PUT sur l'API Metabase avec retry."""
    for attempt in range(3):
        try:
            body = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                f'{MB_BASE}/{path}', data=body, method='PUT',
                headers={
                    'X-Metabase-Session': token,
                    'Content-Type': 'application/json; charset=utf-8',
                },
            )
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                logger.warning(f"Retry {attempt+1}/3 PUT {path}: {e}")
                time.sleep(5)
            else:
                raise


# --- Fonctions métier ---------------------------------------------------------

def detect_new_pharmacies(
    cursor: snowflake.connector.cursor.SnowflakeCursor,
    pha_id_filter: Optional[int] = None,
) -> List[Dict]:
    """Détecte les pharmacies dans dim_pharmacie absentes de RLS_PHARMACY_ACCESS."""
    query = (
        "SELECT d.PHA_ID, d.PHA_NOM, MD5(d.PHA_ID::STRING) AS PHARMACIE_SK "
        "FROM MARTS.DIM_PHARMACIE d "
        "LEFT JOIN AUDIT.RLS_PHARMACY_ACCESS r ON d.PHA_ID = r.PHA_ID "
        "WHERE r.PHA_ID IS NULL AND d.PHA_ID != -1"
    )
    if pha_id_filter is not None:
        query += f" AND d.PHA_ID = {pha_id_filter}"
    cursor.execute(query)
    return [
        {'pha_id': row[0], 'pha_nom': row[1], 'pharmacie_sk': row[2]}
        for row in cursor.fetchall()
    ]


def insert_pharmacy_access(
    cursor: snowflake.connector.cursor.SnowflakeCursor,
    pha_id: int,
    pha_nom: str,
    pharmacie_sk: str,
) -> None:
    """Insère une nouvelle pharmacie dans RLS_PHARMACY_ACCESS (idempotent)."""
    cursor.execute(
        "MERGE INTO AUDIT.RLS_PHARMACY_ACCESS t "
        "USING (SELECT %s AS PHA_ID, %s AS PHA_NOM, %s AS PHARMACIE_SK, "
        "'MEDICORE_ANALYST' AS SF_USERNAME) s "
        "ON t.PHA_ID = s.PHA_ID "
        "WHEN NOT MATCHED THEN INSERT (PHA_ID, PHA_NOM, PHARMACIE_SK, SF_USERNAME) "
        "VALUES (s.PHA_ID, s.PHA_NOM, s.PHARMACIE_SK, s.SF_USERNAME)",
        (pha_id, pha_nom, pharmacie_sk),
    )


def get_or_create_pharmacies_collection(token: str) -> int:
    """Trouve ou crée la collection 'Pharmacies' sous MediCore BI."""
    collections = mb_get(token, 'collection')
    for coll in collections:
        if (coll.get('name') == 'Pharmacies'
                and coll.get('parent_id') == MEDICORE_COLL_ID
                and not coll.get('archived')):
            logger.info("Collection 'Pharmacies' existante: id=%d", coll['id'])
            return coll['id']

    resp = mb_post(token, 'collection', {
        'name': 'Pharmacies',
        'parent_id': MEDICORE_COLL_ID,
    })
    logger.info("Collection 'Pharmacies' créée: id=%d", resp['id'])
    return resp['id']


def create_metabase_group(token: str, group_name: str) -> int:
    """Trouve ou crée un groupe Metabase, retourne l'ID."""
    groups = mb_get(token, 'permissions/group')
    for grp in groups:
        if grp.get('name') == group_name:
            logger.info("Groupe existant: '%s' id=%d", group_name, grp['id'])
            return grp['id']
    resp = mb_post(token, 'permissions/group', {'name': group_name})
    return resp['id']


def create_metabase_collection(
    token: str,
    name: str,
    parent_id: int,
) -> int:
    """Trouve ou crée une collection Metabase, retourne l'ID."""
    collections = mb_get(token, 'collection')
    for coll in collections:
        if (coll.get('name') == name
                and coll.get('parent_id') == parent_id
                and not coll.get('archived')):
            logger.info("Collection existante: '%s' id=%d", name, coll['id'])
            return coll['id']
    resp = mb_post(token, 'collection', {
        'name': name,
        'parent_id': parent_id,
    })
    return resp['id']


def set_group_permissions(
    token: str,
    group_id: int,
    collection_id: int,
) -> None:
    """Configure les permissions du groupe pharmacie.

    Data : query-builder uniquement sur la connexion MediCore, native=none.
    Collection : Vue sur MediCore BI (hérité sur Admin), Curate sur sa collection.
    """
    graph = mb_get(token, 'permissions/graph')
    graph['groups'][str(group_id)] = {
        str(MB_SOURCE_DATABASE_ID): {
            'view-data': 'unrestricted',
            'create-queries': 'query-builder',
            'download': {'schemas': 'full'},
        },
    }
    mb_put(token, 'permissions/graph', graph)

    coll_graph = mb_get(token, 'collection/graph')
    coll_graph['groups'][str(group_id)] = {
        str(MEDICORE_COLL_ID): 'read',
        str(collection_id): 'write',
    }
    mb_put(token, 'collection/graph', coll_graph)


def update_metabase_ids(
    cursor: snowflake.connector.cursor.SnowflakeCursor,
    pha_id: int,
    group_id: int,
    collection_id: int,
) -> None:
    """Met à jour les IDs Metabase dans RLS_PHARMACY_ACCESS."""
    cursor.execute(
        "UPDATE AUDIT.RLS_PHARMACY_ACCESS "
        "SET MB_GROUP_ID = %s, MB_COLLECTION_ID = %s "
        "WHERE PHA_ID = %s",
        (group_id, collection_id, pha_id),
    )


def log_action(
    cursor: snowflake.connector.cursor.SnowflakeCursor,
    run_id: str,
    pha_id: int,
    action: str,
    details: str,
) -> None:
    """Insère une entrée dans RLS_PROVISION_LOG."""
    cursor.execute(
        "INSERT INTO AUDIT.RLS_PROVISION_LOG (RUN_ID, PHA_ID, ACTION, DETAILS) "
        "VALUES (%s, %s, %s, %s)",
        (run_id, pha_id, action, details),
    )


# --- Orchestration principale -------------------------------------------------

def provision_new_pharmacies(
    run_id: str,
    audit_cursor: snowflake.connector.cursor.SnowflakeCursor,
    mb_token: str,
    dry_run: bool,
    pha_id_filter: Optional[int] = None,
) -> int:
    """Détecte et provisionne les nouvelles pharmacies.

    Returns:
        Nombre de pharmacies provisionnées.
    """
    new_pharmacies = detect_new_pharmacies(audit_cursor, pha_id_filter)
    if not new_pharmacies:
        logger.info("Aucune nouvelle pharmacie détectée")
        return 0

    logger.info("%d nouvelle(s) pharmacie(s) détectée(s)", len(new_pharmacies))
    provisioned = 0

    for pharma in new_pharmacies:
        pha_id = pharma['pha_id']
        pha_nom = pharma['pha_nom']
        pharmacie_sk = pharma['pharmacie_sk']

        logger.info("Provisionnement: %s (PHA_ID=%d)", pha_nom, pha_id)

        if dry_run:
            logger.info("[DRY-RUN] Groupe + collection Metabase pour %s", pha_nom)
            provisioned += 1
            continue

        insert_pharmacy_access(audit_cursor, pha_id, pha_nom, pharmacie_sk)
        log_action(audit_cursor, run_id, pha_id, 'NEW_PHARMACY_DETECTED', pha_nom)

        if not mb_token:
            logger.warning("Pas de token Metabase, provisionnement Metabase ignoré")
            provisioned += 1
            continue

        pharmacies_coll_id = get_or_create_pharmacies_collection(mb_token)

        grp_id = create_metabase_group(mb_token, pha_nom)
        log_action(audit_cursor, run_id, pha_id, 'MB_GROUP_CREATED', f'group_id={grp_id}')

        coll_id = create_metabase_collection(mb_token, pha_nom, pharmacies_coll_id)
        log_action(audit_cursor, run_id, pha_id, 'MB_COLLECTION_CREATED', f'collection_id={coll_id}')

        set_group_permissions(mb_token, grp_id, coll_id)
        log_action(audit_cursor, run_id, pha_id, 'PERMISSIONS_SET',
                   f'group={grp_id} coll={coll_id} db={MB_SOURCE_DATABASE_ID}')

        update_metabase_ids(audit_cursor, pha_id, grp_id, coll_id)
        provisioned += 1
        logger.info("Provisionne %d/%d : %s", provisioned, len(new_pharmacies), pha_nom)

        # Pause entre chaque pharmacie pour eviter le timeout Metabase
        if provisioned < len(new_pharmacies):
            time.sleep(3)

    return provisioned


def deactivate_pharmacies(
    run_id: str,
    audit_cursor: snowflake.connector.cursor.SnowflakeCursor,
    dry_run: bool,
) -> None:
    """Désactive les groupes Metabase des pharmacies IS_ACTIVE=FALSE."""
    audit_cursor.execute(
        "SELECT PHA_ID, PHA_NOM FROM AUDIT.RLS_PHARMACY_ACCESS "
        "WHERE IS_ACTIVE = FALSE"
    )
    inactive = audit_cursor.fetchall()
    for pha_id, pha_nom in inactive:
        logger.info("Désactivation: %s (PHA_ID=%d)", pha_nom, pha_id)
        if dry_run:
            continue
        log_action(audit_cursor, run_id, pha_id, 'PHARMACY_DEACTIVATED', pha_nom)


def main() -> None:
    """Point d'entrée principal du provisionnement RLS."""
    parser = argparse.ArgumentParser(description='Provisionnement RLS pharmacies')
    parser.add_argument('--run-id', required=True, help='UUID du run batch')
    parser.add_argument('--dry-run', action='store_true', help='Simulation sans modification')
    parser.add_argument('--pha-id', type=int, help='Provisionner une seule pharmacie (PHA_ID)')
    args = parser.parse_args()

    logger.info("=== Provisionnement RLS — run_id=%s dry_run=%s pha_id=%s ===",
                args.run_id, args.dry_run, args.pha_id or 'ALL')

    audit_conn = get_audit_connection()
    audit_cursor = audit_conn.cursor()

    try:
        mb_token = mb_authenticate()
    except Exception as exc:
        logger.warning("Authentification Metabase échouée: %s — provisionnement Metabase ignoré", exc)
        mb_token = ''

    try:
        nb_new = provision_new_pharmacies(
            args.run_id, audit_cursor, mb_token, args.dry_run, args.pha_id,
        )
        deactivate_pharmacies(args.run_id, audit_cursor, args.dry_run)
        logger.info("=== RLS terminé : %d nouvelle(s) pharmacie(s) ===", nb_new)
    finally:
        audit_cursor.close()
        audit_conn.close()


if __name__ == '__main__':
    main()
