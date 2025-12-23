# Infra-Mapper - Guide de démarrage rapide

Ce guide vous permettra d'installer et configurer Infra-Mapper en moins de 10 minutes.

## Prérequis

- **Serveur** : Debian 11/12, Ubuntu 22.04+ ou similaire
- **Docker** : Docker Engine 24+ avec Docker Compose v2
- **Réseau** : Ports 8080 (ou personnalisé) et 22 (SSH pour déploiement agents)

## Installation

### 1. Cloner le projet

```bash
git clone https://github.com/votre-repo/infra-mapper.git
cd infra-mapper
```

### 2. Configuration

```bash
# Copier le fichier de configuration
cp .env.example .env

# Générer des clés sécurisées
API_KEY=$(openssl rand -hex 16)
SECRET_KEY=$(openssl rand -hex 32)

# Configurer le fichier .env (remplacez les valeurs)
sed -i "s/your-secure-db-password-here/$(openssl rand -hex 12)/" .env
sed -i "s/your-secure-api-key-here/$API_KEY/" .env
sed -i "s/your-jwt-secret-key-here/$SECRET_KEY/" .env
sed -i "s/your-admin-password-here/$(openssl rand -base64 12)/" .env
sed -i "s/your-server-ip/$(hostname -I | awk '{print $1}')/" .env

# Vérifier la configuration
cat .env
```

### 3. Préparer le dossier SSH (pour déployer les agents)

```bash
mkdir -p ssh-keys
chmod 700 ssh-keys
```

> **Note** : La clé SSH peut être générée directement depuis l'interface web dans **Paramètres > Clés SSH > Générer une clé SSH**. La génération en ligne de commande est optionnelle.

### 4. Démarrer Infra-Mapper

**Option A : PostgreSQL inclus (simple)**

```bash
docker compose -f docker-compose.prod.yml up -d

# Vérifier que tout fonctionne
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
```

**Option B : PostgreSQL externe**

Si vous avez déjà un serveur PostgreSQL :

```bash
# 1. Créer la base sur votre serveur PostgreSQL
psql -h votre-postgres -U postgres -c "CREATE USER infra_mapper WITH PASSWORD 'votre-mdp';"
psql -h votre-postgres -U postgres -c "CREATE DATABASE infra_mapper OWNER infra_mapper;"

# 2. Configurer le .env
cat >> .env << EOF
MAPPER_DB_HOST=votre-postgres
MAPPER_DB_PORT=5432
MAPPER_DB_USER=infra_mapper
MAPPER_DB_PASSWORD=votre-mdp
MAPPER_DB_NAME=infra_mapper
EOF

# 3. Utiliser docker-compose.yml (sans service postgres)
docker compose up -d
```

> **Note** : Le schéma de la base de données (26 tables) est créé automatiquement au premier démarrage.

> **Astuce Tailscale** : Si les firewalls bloquent le port 5432, utilisez les IPs Tailscale pour la communication entre serveurs (ex: `MAPPER_DB_HOST=100.64.0.3`).

### 5. Accéder à l'interface

Ouvrez votre navigateur : **http://votre-serveur:8080**

Connectez-vous avec les identifiants configurés dans `.env` :
- Username : `admin` (ou valeur de `MAPPER_INITIAL_ADMIN_USERNAME`)
- Password : valeur de `MAPPER_INITIAL_ADMIN_PASSWORD`

## Déployer des agents

Les agents collectent les informations Docker sur vos serveurs distants.

### Option 1 : Script automatique (recommandé)

```bash
# Exporter les variables pour le script
export MAPPER_BACKEND_URL="http://$(hostname -I | awk '{print $1}'):8080"
export MAPPER_API_KEY="$(grep MAPPER_API_KEY .env | cut -d= -f2)"

# Déployer sur un serveur distant
./deploy-agent.sh 192.168.1.25 root 22

# Ou avec Tailscale
./deploy-agent.sh 100.64.0.5 root 22
```

### Option 2 : Installation manuelle

Sur le serveur distant :

```bash
# Créer le répertoire
mkdir -p /opt/infra-mapper-agent

# Copier les fichiers (depuis le serveur Infra-Mapper)
scp -r agent/* root@192.168.1.25:/opt/infra-mapper-agent/

# Créer le fichier .env
cat > /opt/infra-mapper-agent/.env << EOF
MAPPER_BACKEND_URL=http://votre-serveur:8080
MAPPER_API_KEY=votre-api-key
MAPPER_SCAN_INTERVAL=90
MAPPER_LOG_LEVEL=INFO
MAPPER_TAILSCALE_ENABLED=true
MAPPER_TCPDUMP_ENABLED=true
MAPPER_TCPDUMP_MODE=intermittent
EOF

# Créer docker-compose.yml
cat > /opt/infra-mapper-agent/docker-compose.yml << 'EOF'
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
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - /var/run/tailscale:/var/run/tailscale:ro
      - /proc:/host/proc:ro
    env_file:
      - .env
EOF

# Démarrer l'agent
cd /opt/infra-mapper-agent
docker compose up -d --build
```

## Vérification

### Santé des agents

```bash
# Via l'API
curl http://localhost:8080/api/v1/agents/health/summary | jq .

# Ou dans l'interface : Menu "Santé Agents"
```

### Logs

```bash
# Backend
docker compose -f docker-compose.prod.yml logs -f backend

# Agent (sur le serveur distant)
ssh root@192.168.1.25 "docker logs -f infra-mapper-agent"
```

## Configuration avancée

### Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name infra.example.com;

    ssl_certificate /etc/ssl/certs/infra.crt;
    ssl_certificate_key /etc/ssl/private/infra.key;

    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Mettre à jour `.env` :
```env
MAPPER_CORS_ORIGINS=["https://infra.example.com"]
MAPPER_TRUSTED_HOSTS=["infra.example.com"]
MAPPER_BACKEND_URL=https://infra.example.com
```

### Tailscale

Si vous utilisez Tailscale, utilisez les IPs Tailscale pour la communication :

```env
MAPPER_BACKEND_URL=http://100.64.0.1:8080
```

## Dépannage

### L'agent ne se connecte pas

1. Vérifier la connectivité :
   ```bash
   curl http://votre-serveur:8080/health
   ```

2. Vérifier l'API key :
   ```bash
   curl -H "X-API-Key: votre-api-key" http://votre-serveur:8080/api/v1/hosts
   ```

3. Vérifier les logs de l'agent :
   ```bash
   docker logs infra-mapper-agent
   ```

### Agent en état "Degraded"

L'agent peut être marqué "degraded" si les rapports prennent trop de temps :
- Augmenter `MAPPER_SCAN_INTERVAL` (90s recommandé avec tcpdump)
- Vérifier les ressources du serveur

### Pas de connexions réseau détectées

Vérifier que tcpdump fonctionne :
```bash
docker exec infra-mapper-agent tcpdump -c 5 -n
```

### Base de données inaccessible

Si la connexion PostgreSQL échoue :

1. Vérifier la connectivité réseau :
   ```bash
   nc -zv votre-postgres 5432
   ```

2. Si le port est bloqué par un firewall (Tailscale, iptables), utilisez les IPs Tailscale :
   ```bash
   # Obtenir l'IP Tailscale du serveur PostgreSQL
   tailscale ip -4

   # Configurer le .env avec l'IP Tailscale
   MAPPER_DB_HOST=100.64.0.x
   ```

3. Vérifier que PostgreSQL écoute sur toutes les interfaces (`listen_addresses = '*'` dans postgresql.conf)

## Ressources

- [Documentation complète](README.md)
- [API Reference](docs/api.md)
- [Changelog](CHANGELOG.md)

## Support

En cas de problème, ouvrez une issue sur le dépôt GitHub avec :
- Version d'Infra-Mapper
- Logs du backend et de l'agent
- Configuration (sans les secrets)
