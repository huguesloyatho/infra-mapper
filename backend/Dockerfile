FROM python:3.12-slim

WORKDIR /app

# Installer les outils système nécessaires (SSH, curl pour healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    sshpass \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . .

# Variables d'environnement par défaut
ENV MAPPER_DB_HOST=postgres
ENV MAPPER_DB_PORT=5432
ENV MAPPER_DB_NAME=infra_mapper
ENV MAPPER_DB_USER=postgres
ENV MAPPER_DB_PASSWORD=postgres

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
