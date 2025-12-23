#!/bin/bash
# Script de déploiement de clé SSH et mise à jour des agents
# Usage: ./deploy-agent.sh <host> [user] [port]

set -e

HOST=$1
USER=${2:-root}
PORT=${3:-22}

if [ -z "$HOST" ]; then
    echo "Usage: $0 <host> [user] [port]"
    echo "Example: $0 192.168.1.25 root 22"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/agent"
SSH_KEY="$SCRIPT_DIR/ssh-keys/id_ed25519.pub"
REMOTE_AGENT_PATH="/opt/infra-mapper-agent"

echo "=== Déploiement sur $USER@$HOST:$PORT ==="

# 1. Déployer la clé SSH si elle existe
if [ -f "$SSH_KEY" ]; then
    echo ">> Déploiement de la clé SSH..."
    PUBLIC_KEY=$(cat "$SSH_KEY")

    ssh -o StrictHostKeyChecking=no -p "$PORT" "$USER@$HOST" "
        mkdir -p ~/.ssh
        chmod 700 ~/.ssh
        echo '$PUBLIC_KEY' >> ~/.ssh/authorized_keys
        sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys
        chmod 600 ~/.ssh/authorized_keys
    "
    echo "   Clé SSH déployée"
else
    echo "   Pas de clé SSH à déployer"
fi

# 2. Créer le répertoire agent
echo ">> Création du répertoire agent..."
ssh -o StrictHostKeyChecking=no -p "$PORT" "$USER@$HOST" "mkdir -p $REMOTE_AGENT_PATH/collectors"

# 3. Copier les fichiers de l'agent
echo ">> Copie des fichiers de l'agent..."
scp -o StrictHostKeyChecking=no -P "$PORT" \
    "$AGENT_DIR/agent.py" \
    "$AGENT_DIR/config.py" \
    "$AGENT_DIR/models.py" \
    "$AGENT_DIR/command_server.py" \
    "$AGENT_DIR/requirements.txt" \
    "$AGENT_DIR/Dockerfile" \
    "$USER@$HOST:$REMOTE_AGENT_PATH/"

# Copier les collectors
scp -o StrictHostKeyChecking=no -P "$PORT" \
    "$AGENT_DIR/collectors/"*.py \
    "$USER@$HOST:$REMOTE_AGENT_PATH/collectors/"

# 4. Créer le docker-compose.yml
echo ">> Création du docker-compose.yml..."
ssh -o StrictHostKeyChecking=no -p "$PORT" "$USER@$HOST" "cat > $REMOTE_AGENT_PATH/docker-compose.yml << 'EOF'
version: '3.8'

services:
  agent:
    build: .
    container_name: infra-mapper-agent
    restart: unless-stopped
    network_mode: host
    pid: host
    cap_add:
      - NET_ADMIN
      - NET_RAW
      - SYS_PTRACE
      - SYS_ADMIN
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /root:/root:ro
      - /home:/home:ro
      - /opt:/opt:ro
      - /srv:/srv:ro
      - /var/run/tailscale:/var/run/tailscale:ro
      - /proc:/host/proc:ro
    env_file:
      - .env
EOF"

# 5. Créer le fichier .env
BACKEND_URL=${MAPPER_BACKEND_URL:-"http://192.168.1.30:8080"}
API_KEY=${MAPPER_API_KEY:-"change-me-in-production"}

echo ">> Création du fichier .env..."
ssh -o StrictHostKeyChecking=no -p "$PORT" "$USER@$HOST" "cat > $REMOTE_AGENT_PATH/.env << EOF
MAPPER_BACKEND_URL=$BACKEND_URL
MAPPER_API_KEY=$API_KEY
MAPPER_SCAN_INTERVAL=90
MAPPER_LOG_LEVEL=INFO
MAPPER_TAILSCALE_ENABLED=true
MAPPER_TCPDUMP_ENABLED=true
MAPPER_TCPDUMP_MODE=intermittent
MAPPER_COLLECT_LOGS=true
MAPPER_LOGS_LINES=100
MAPPER_LOGS_SINCE_SECONDS=60
EOF"

# 6. Build et démarrer l'agent
echo ">> Build et démarrage de l'agent..."
ssh -o StrictHostKeyChecking=no -p "$PORT" "$USER@$HOST" "
    cd $REMOTE_AGENT_PATH && \
    docker compose down 2>/dev/null || true && \
    docker compose up -d --build
"

# 7. Vérifier le statut
echo ">> Vérification du statut..."
sleep 3
ssh -o StrictHostKeyChecking=no -p "$PORT" "$USER@$HOST" "cd $REMOTE_AGENT_PATH && docker compose ps"

echo ""
echo "=== Déploiement terminé sur $HOST ==="
echo "Les logs de l'agent: ssh $USER@$HOST 'cd $REMOTE_AGENT_PATH && docker compose logs -f'"
