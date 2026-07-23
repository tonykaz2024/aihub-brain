FROM python:3.12-slim

# Dependințe sistem
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git sqlite3 openssh-client docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Memoria incidentelor
RUN mkdir -p /app/memory /app/logs

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "agents.orchestrator"]

# Schema SQL baked in imagine (nu depinde de mount)
COPY memory/schema.sql /app/memory/schema.sql
