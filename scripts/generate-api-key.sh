#!/bin/bash
# Génère une clé API sécurisée

API_KEY=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
echo "Clé API générée: $API_KEY"
echo ""
echo "Ajoutez cette ligne à votre .env:"
echo "MAPPER_API_KEY=$API_KEY"
