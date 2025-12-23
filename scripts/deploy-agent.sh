#!/bin/bash
# Script de déploiement de l'agent Infra-Mapper sur un hôte distant
# Usage: ./deploy-agent.sh user@host [backend_url] [api_key]

set -e

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Arguments
TARGET_HOST="${1:-}"
BACKEND_URL="${2:-http://localhost:8080}"
API_KEY="${3:-change-me-in-production}"

if [ -z "$TARGET_HOST" ]; then
    echo -e "${RED}Usage: $0 user@host [backend_url] [api_key]${NC}"
    echo "Exemple: $0 root@192.168.1.25 http://infra-mapper.local:8080 my-api-key"
    exit 1
fi

echo -e "${GREEN}=== Déploiement de l'agent Infra-Mapper ===${NC}"
echo "Cible: $TARGET_HOST"
echo "Backend: $BACKEND_URL"

# Dossier de travail sur l'hôte distant
REMOTE_DIR="/opt/infra-mapper-agent"

echo -e "${YELLOW}[1/4] Création du dossier distant...${NC}"
ssh "$TARGET_HOST" "mkdir -p $REMOTE_DIR"

echo -e "${YELLOW}[2/4] Copie des fichiers de l'agent...${NC}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

scp -r "$PROJECT_DIR/agent/"* "$TARGET_HOST:$REMOTE_DIR/"
scp "$PROJECT_DIR/docker-compose.agent.yml" "$TARGET_HOST:$REMOTE_DIR/docker-compose.yml"

echo -e "${YELLOW}[3/4] Création du fichier .env...${NC}"
ssh "$TARGET_HOST" "cat > $REMOTE_DIR/.env << EOF
MAPPER_BACKEND_URL=$BACKEND_URL
MAPPER_API_KEY=$API_KEY
MAPPER_SCAN_INTERVAL=30
MAPPER_LOG_LEVEL=INFO
MAPPER_TAILSCALE_ENABLED=true
EOF"

echo -e "${YELLOW}[4/4] Démarrage de l'agent...${NC}"
ssh "$TARGET_HOST" "cd $REMOTE_DIR && docker compose down 2>/dev/null || true && docker compose up -d --build"

echo -e "${GREEN}=== Déploiement terminé ===${NC}"
echo "L'agent est maintenant actif sur $TARGET_HOST"
echo ""
echo "Commandes utiles:"
echo "  Logs:     ssh $TARGET_HOST 'docker logs -f infra-mapper-agent-agent-1'"
echo "  Status:   ssh $TARGET_HOST 'docker ps | grep infra-mapper'"
echo "  Arrêter:  ssh $TARGET_HOST 'cd $REMOTE_DIR && docker compose down'"
