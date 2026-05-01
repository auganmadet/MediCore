#!/bin/bash
# ==============================================================================
# Vue synthétique de l'état des topics CDC Kafka MediCore.
#
# Usage :
#   ./scripts/kafka_status.sh          # vue CDC standard (4 topics)
#   ./scripts/kafka_status.sh --all    # tous les topics du cluster
#
# Affiche :
#   - Consumer lag par topic CDC (publié vs consommé)
#   - Timestamp du dernier message publié (freshness)
#   - Alerte si LAG > 0 ou topic absent
#
# Prérequis : docker ps doit voir le conteneur 'kafka' healthy.
# ==============================================================================

set -euo pipefail

# Désactive la conversion de path MSYS (Git Bash Windows) pour docker exec
export MSYS_NO_PATHCONV=1

CONSUMER_GROUP="medi_core_cdc_batch_dev2"
BOOTSTRAP="kafka:29092"
CDC_TOPICS=(
  "winstat_rds.winstat.COMMANDES"
  "winstat_rds.winstat.FACTURES"
  "winstat_rds.winstat.ORDERS"
  "winstat_rds.winstat.MODSTOCK"
)

MODE="${1:-cdc}"

# Vérifie accessibilité Kafka via un appel léger (liste des brokers)
if ! docker exec kafka /usr/bin/kafka-broker-api-versions \
     --bootstrap-server "${BOOTSTRAP}" > /dev/null 2>&1; then
  echo "ERREUR: Kafka inaccessible. Vérifier 'docker ps | grep kafka'."
  exit 1
fi

echo "========================================================================="
echo "  Kafka status MediCore - $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "========================================================================="

# --- Section 1 : topics cibles ---------------------------------------------
if [ "${MODE}" = "--all" ]; then
  echo ""
  echo "Tous les topics (${BOOTSTRAP}) :"
  docker exec kafka /usr/bin/kafka-topics \
    --bootstrap-server "${BOOTSTRAP}" --list 2>/dev/null | sort | sed 's/^/  /'
fi

# --- Section 2 : lag consumer group par topic CDC ---------------------------
echo ""
echo "Consumer group : ${CONSUMER_GROUP}"
echo ""
LAG_OUTPUT=$(docker exec kafka /usr/bin/kafka-consumer-groups \
  --bootstrap-server "${BOOTSTRAP}" \
  --describe --group "${CONSUMER_GROUP}" 2>/dev/null || true)

if [ -z "${LAG_OUTPUT}" ]; then
  echo "  Consumer group absent ou inactif."
else
  echo "${LAG_OUTPUT}" | awk '/^GROUP/ || /winstat_rds\.winstat\./' | column -t | sed 's/^/  /'
fi

# --- Section 3 : freshness (timestamp du dernier message publié) ------------
echo ""
echo "Freshness (timestamp du dernier event publié) :"
for topic in "${CDC_TOPICS[@]}"; do
  END=$(docker exec kafka /usr/bin/kafka-get-offsets \
    --bootstrap-server "${BOOTSTRAP}" --topic "${topic}" --time latest 2>/dev/null \
    | cut -d: -f3 || echo "?")
  if [ -z "${END}" ] || [ "${END}" = "0" ]; then
    printf "  %-40s vide\n" "${topic}"
    continue
  fi
  # Lecture du dernier message pour récupérer son timestamp
  LAST_TS=$(docker exec kafka /usr/bin/kafka-console-consumer \
    --bootstrap-server "${BOOTSTRAP}" \
    --topic "${topic}" --partition 0 --offset $((END - 1)) \
    --max-messages 1 --timeout-ms 3000 \
    --property print.timestamp=true --property print.value=false 2>/dev/null \
    | head -1 | cut -f1 | sed 's/CreateTime://')
  if [ -n "${LAST_TS}" ]; then
    HUMAN=$(date -u -d "@$((LAST_TS / 1000))" '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null || echo "ts=${LAST_TS}")
    printf "  %-40s end=%-10s dernier msg: %s\n" "${topic}" "${END}" "${HUMAN}"
  else
    printf "  %-40s end=%-10s (timestamp indisponible)\n" "${topic}" "${END}"
  fi
done

# --- Section 4 : verdict ----------------------------------------------------
echo ""
if echo "${LAG_OUTPUT}" | grep -E "winstat_rds\.winstat\." | awk '{print $6}' | grep -qE "^[1-9]"; then
  echo "VERDICT : LAG > 0 détecté. Des events Kafka ne sont pas encore consommés."
else
  echo "VERDICT : LAG=0 partout. Consumer à jour."
fi
echo "========================================================================="
