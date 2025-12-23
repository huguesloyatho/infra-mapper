FROM python:3.12-slim

WORKDIR /app

# Installer les dépendances système (incluant gcc pour compiler netifaces, tcpdump + util-linux pour nsenter)
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    gcc \
    python3-dev \
    tcpdump \
    util-linux \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Nettoyer les outils de build pour réduire la taille de l'image
RUN apt-get purge -y gcc python3-dev && apt-get autoremove -y

# Copier le code
COPY . .

# Variables d'environnement par défaut
ENV MAPPER_BACKEND_URL=http://backend:8000
ENV MAPPER_SCAN_INTERVAL=30
ENV MAPPER_LOG_LEVEL=INFO

# Lancer l'agent
CMD ["python", "agent.py"]
