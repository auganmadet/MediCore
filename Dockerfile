# MediCore ELT Pipeline - Multi-stage build
# Premier stage : builder
FROM python:3.11-slim as builder

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
    
WORKDIR /app
COPY --from=builder /root/.local /root/.local
# Ajoute /root/.local/bin au PATH pour pouvoir appeler dbt, python, etc.
ENV PATH=/root/.local/bin:$PATH     

# Copy project
COPY . .
RUN chmod +x scripts/*.sh

# Expose ports (dbt docs)
EXPOSE 8080

# Snowflake connection Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python scripts/healthcheck.py || exit 1

ENTRYPOINT ["./scripts/entrypoint.sh"]

# -----------------------------------

# FROM python:3.11-slim as builder
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir --user -r requirements.txt

# FROM python:3.11-slim
# WORKDIR /app
# COPY --from=builder /root/.local /root/.local
# ENV PATH=/root/.local/bin:$PATH
# COPY . .
# COPY ./scripts/entrypoint.sh ./scripts/entrypoint.sh
# RUN chmod +x ./scripts/entrypoint.sh
# ENTRYPOINT ["./scripts/entrypoint.sh"]
