# MediCore ELT Pipeline - Multi-stage build
# Premier stage : builder
FROM python:3.11-slim AS builder

# Installer git (nécessaire pour dbt deps / packages.yml)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Second stage : sans les fichiers de build
FROM python:3.11-slim

# Installer git + curl dans l'image finale (git: dbt deps, curl: alertes Teams webhook)
RUN apt-get update && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

# Utilisateur non-root pour le runtime
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -s /bin/bash -m appuser

WORKDIR /app
COPY --from=builder /root/.local /home/appuser/.local
RUN chown -R appuser:appuser /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy project
COPY --chown=appuser:appuser . .
RUN chmod +x scripts/*.sh

# Repertoires de travail pour dbt et logs
RUN mkdir -p /home/appuser/.dbt /app/logs /app/dbt/logs /app/dbt/target /app/dbt/dbt_packages && \
    chown -R appuser:appuser /home/appuser/.dbt /app/logs /app/dbt/logs /app/dbt/target /app/dbt/dbt_packages

# Expose ports (dbt docs)
EXPOSE 8080

USER appuser

# Installer les dépendances dbt en tant que appuser (permissions correctes)
RUN cd /app/dbt && dbt deps --target dev 2>/dev/null || true

# Snowflake connection Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python scripts/healthcheck.py || exit 1

ENTRYPOINT ["./scripts/entrypoint.sh"]
