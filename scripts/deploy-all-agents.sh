#!/bin/bash
# Déploie l'agent sur plusieurs hôtes
# Usage: ./deploy-all-agents.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Charger le fichier .env s'il existe
ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "Chargement de la configuration depuis $ENV_FILE"
    export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)
fi

# Configuration (depuis .env ou valeurs par défaut)
BACKEND_URL="${MAPPER_BACKEND_URL:-}"
API_KEY="${MAPPER_API_KEY:-}"

# Vérification des variables obligatoires
if [ -z "$BACKEND_URL" ]; then
    echo "ERREUR: MAPPER_BACKEND_URL n'est pas défini dans .env"
    echo "Exemple: MAPPER_BACKEND_URL=http://192.168.1.30:8080"
    exit 1
fi

if [ -z "$API_KEY" ] || [ "$API_KEY" = "change-me-in-production" ]; then
    echo "ERREUR: MAPPER_API_KEY n'est pas défini ou utilise la valeur par défaut"
    echo "Générez une clé avec: ./scripts/generate-api-key.sh"
    exit 1
fi

# Liste des hôtes (depuis .env ou liste par défaut)
# Format dans .env: MAPPER_HOSTS="root@192.168.1.25,root@192.168.1.30"
if [ -n "$MAPPER_HOSTS" ]; then
    IFS=',' read -ra HOSTS <<< "$MAPPER_HOSTS"
else
    # Liste par défaut - à personnaliser
    HOSTS=(
        "root@192.168.1.25"   # nextcloud / postgres
        "root@192.168.1.30"   # mac-mini-m1 / n8n
        # Ajoutez vos autres hôtes ici
    )
fi

echo "=== Déploiement des agents Infra-Mapper ==="
echo "Backend URL: $BACKEND_URL"
echo "API Key: ${API_KEY:0:8}..."
echo "Hôtes: ${#HOSTS[@]}"
echo ""

for host in "${HOSTS[@]}"; do
    echo "----------------------------------------"
    echo "Déploiement sur: $host"
    "$SCRIPT_DIR/deploy-agent.sh" "$host" "$BACKEND_URL" "$API_KEY"
    echo ""
done

echo "=== Tous les agents ont été déployés ==="
