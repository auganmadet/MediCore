"""Utilitaire monitoring lag Kafka : mesure le retard du consumer CDC.

Calcule le lag (end_offset - committed_offset) par topic et partition.
Écrit les métriques dans un fichier lisible par bash et dans AUDIT.CDC_LAG_METRICS.
Encapsulé dans try/except — ne doit jamais casser le pipeline.
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from kafka import KafkaConsumer, TopicPartition

logger = logging.getLogger(__name__)


def get_consumer_lag(
    bootstrap_servers: str,
    group_id: str,
    topics: List[str],
) -> Dict[str, int]:
    """Calcule le lag (end_offset - committed) par topic Kafka.

    Crée un consumer temporaire avec assign() (pas de rebalance)
    pour lire uniquement les metadata d'offsets.

    Args:
        bootstrap_servers: Adresse Kafka (host:port).
        group_id: Group ID du consumer CDC.
        topics: Liste des topics à vérifier.

    Returns:
        Dict topic -> lag agrégé + clé 'total'. Dict vide en cas d'erreur.
    """
    try:
        consumer = KafkaConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=False,
            consumer_timeout_ms=5000,
        )

        all_partitions: List[TopicPartition] = []
        for topic in topics:
            partitions = consumer.partitions_for_topic(topic)
            if partitions is None:
                logger.warning(f"Topic introuvable: {topic}")
                continue
            for p in partitions:
                all_partitions.append(TopicPartition(topic, p))

        if not all_partitions:
            consumer.close()
            return {}

        consumer.assign(all_partitions)
        end_offsets = consumer.end_offsets(all_partitions)

        lag_by_topic: Dict[str, int] = {}
        total_lag = 0

        for tp in all_partitions:
            end = end_offsets.get(tp, 0)
            committed = consumer.committed(tp)
            partition_lag = end - (committed if committed is not None else 0)

            topic_name = tp.topic
            lag_by_topic[topic_name] = lag_by_topic.get(topic_name, 0) + partition_lag
            total_lag += partition_lag

        lag_by_topic['total'] = total_lag
        consumer.close()

        logger.info(f"Kafka lag total: {total_lag} records ({len(all_partitions)} partitions)")
        return lag_by_topic

    except Exception as exc:
        logger.warning(f"Calcul lag Kafka échoué (non bloquant): {exc}")
        return {}


def write_lag_metrics(lag_by_topic: Dict[str, int]) -> None:
    """Écrit les métriques de lag dans /tmp/cdc_lag_metrics.

    Format : une ligne par topic (topic=lag), lisible par bash
    via grep '^total=' | cut -d= -f2.

    Args:
        lag_by_topic: Dict topic -> lag (incluant clé 'total').
    """
    try:
        with open('/tmp/cdc_lag_metrics', 'w') as f:
            for topic, lag in lag_by_topic.items():
                f.write(f"{topic}={lag}\n")
    except OSError as exc:
        logger.warning(f"Écriture /tmp/cdc_lag_metrics échouée: {exc}")


def log_lag_to_audit(run_id: str, lag_by_topic: Dict[str, int]) -> None:
    """Insère les métriques de lag dans AUDIT.CDC_LAG_METRICS.

    Une ligne par topic (exclut la clé 'total' synthétique).
    Pattern identique à audit.py : connexion éphémère, try/except, non bloquant.

    Args:
        run_id: Identifiant unique du run pipeline.
        lag_by_topic: Dict topic -> lag.
    """
    import snowflake.connector

    try:
        conn = snowflake.connector.connect(
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            database=os.getenv('SNOWFLAKE_DATABASE', 'MEDIcore'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE_NAME', 'MEDIcore_WH'),
            schema='AUDIT',
        )
        cursor = conn.cursor()

        rows = [
            (run_id, topic, lag)
            for topic, lag in lag_by_topic.items()
            if topic != 'total'
        ]
        if rows:
            cursor.executemany(
                "INSERT INTO CDC_LAG_METRICS (RUN_ID, TOPIC, LAG) VALUES (%s, %s, %s)",
                rows,
            )

        cursor.close()
        conn.close()
        logger.info(f"Audit lag: {len(rows)} topics enregistrés")
    except Exception as exc:
        logger.warning(f"Audit log_lag_to_audit échoué (non bloquant): {exc}")
