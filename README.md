# Infra-Mapper

<p align="center">
  <img src="frontend/public/favicon.svg" alt="Infra-Mapper Logo" width="128" height="128">
</p>

<p align="center">
  <strong>Solution de cartographie dynamique d'infrastructure Docker multi-hôtes</strong>
</p>

<p align="center">
  Visualisez en temps réel vos conteneurs Docker, leurs connexions réseau et leurs dépendances à travers plusieurs serveurs.
</p>

<p align="center">
  <a href="#fonctionnalités">Fonctionnalités</a> •
  <a href="#screenshots">Screenshots</a> •
  <a href="#démarrage-rapide">Installation</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#api-rest">API</a>
</p>

---

## Screenshots

<p align="center">
  <img src="docs/screenshots/graph.png" alt="Infrastructure Graph" width="100%">
  <br><em>Vue graphe - Visualisation interactive de l'infrastructure avec connexions réseau</em>
</p>

<p align="center">
  <img src="docs/screenshots/inventory.png" alt="Inventory View" width="100%">
  <br><em>Inventaire - Vue détaillée des conteneurs par hôte avec statut et ports</em>
</p>

<p align="center">
  <img src="docs/screenshots/metrics.png" alt="Metrics Dashboard" width="100%">
  <br><em>Métriques - Monitoring CPU, RAM, Disque en temps réel</em>
</p>

<p align="center">
  <img src="docs/screenshots/logs.png" alt="Container Logs" width="100%">
  <br><em>Logs - Consultation centralisée des logs de conteneurs</em>
</p>

<p align="center">
  <img src="docs/screenshots/vms.png" alt="VM Management" width="100%">
  <br><em>Gestion VMs - Déploiement et gestion des agents</em>
</p>

---

## Fonctionnalités

### Découverte et monitoring
- **Découverte automatique** des conteneurs Docker sur plusieurs hôtes
- **Détection des connexions réseau** entre conteneurs et services externes (tcpdump)
- **Support Tailscale** natif avec mapping automatique des IPs
- **Parsing docker-compose** pour les dépendances déclarées
- **Métriques temps-réel** : CPU, mémoire, disque, réseau
- **Historique des métriques** avec export Prometheus

### Interface utilisateur
- **Visualisation interactive** avec Cytoscape.js
- **Mises à jour temps réel** via WebSocket
- **Dashboards personnalisables** (sauvegarde des layouts)
- **Filtrage** par hôte, projet ou état
- **Export PNG** du graphe d'infrastructure
- **Mode sombre** intégré

### Sécurité et gestion
- **Authentification JWT** avec 2FA (TOTP)
- **SSO** : OIDC et SAML supportés
- **Multi-organisation** avec équipes et rôles
- **Audit logging** complet
- **Alertes** configurables avec webhooks (Slack, Discord, Telegram, ntfy, etc.)
- **Rate limiting** et headers de sécurité

### Observabilité
- **Santé des agents** avec détection de dégradation
- **Métriques internes** du backend (latence, erreurs)
- **Export Prometheus** (`/api/v1/metrics/prometheus`)
- **Logs des conteneurs** centralisés

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Infrastructure                          │
├───────────────┬───────────────┬───────────────┬─────────────┤
│    Host 1     │    Host 2     │    Host 3     │    ...      │
│    Agent      │    Agent      │    Agent      │   Agent     │
│  (Python)     │  (Python)     │  (Python)     │             │
└───────┬───────┴───────┬───────┴───────┬───────┴──────┬──────┘
        │               │               │              │
        └───────────────┴───────┬───────┴──────────────┘
                                │ HTTP/Tailscale
                         ┌──────▼──────┐
                         │   Nginx     │ :8080
                         ├─────────────┤
                         │  Frontend   │ (Vue.js + Cytoscape)
                         ├─────────────┤
                         │   Backend   │ (FastAPI)
                         ├─────────────┤
                         │ PostgreSQL  │ (inclus ou externe)
                         └─────────────┘
```

## Démarrage rapide

**→ Voir [QUICKSTART.md](QUICKSTART.md) pour un guide détaillé**

### Option 1 : PostgreSQL inclus (simple)

```bash
# 1. Cloner et configurer
git clone https://github.com/votre-username/infra-mapper.git
cd infra-mapper
cp .env.example .env

# 2. Générer des clés sécurisées
sed -i "s/your-secure-db-password-here/$(openssl rand -hex 12)/" .env
sed -i "s/your-secure-api-key-here/$(openssl rand -hex 16)/" .env
sed -i "s/your-jwt-secret-key-here/$(openssl rand -hex 32)/" .env
sed -i "s/your-admin-password-here/ChangeMe123!/" .env
sed -i "s/your-server-ip/$(hostname -I | awk '{print $1}')/" .env

# 3. Préparer le dossier SSH (clés générables depuis l'interface)
mkdir -p ssh-keys && chmod 700 ssh-keys

# 4. Démarrer
docker compose -f docker-compose.prod.yml up -d

# 5. Accéder à l'interface
echo "URL: http://$(hostname -I | awk '{print $1}'):8080"
```

### Option 2 : PostgreSQL externe

```bash
# 1. Créer la base de données sur votre serveur PostgreSQL
psql -h votre-postgres -U postgres -c "CREATE USER infra_mapper WITH PASSWORD 'votre-mdp';"
psql -h votre-postgres -U postgres -c "CREATE DATABASE infra_mapper OWNER infra_mapper;"

# 2. Configurer le .env
MAPPER_DB_HOST=votre-postgres    # IP ou hostname (Tailscale supporté)
MAPPER_DB_PORT=5432
MAPPER_DB_USER=infra_mapper
MAPPER_DB_PASSWORD=votre-mdp
MAPPER_DB_NAME=infra_mapper

# 3. Utiliser docker-compose.yml (sans service postgres)
docker compose up -d
```

> **Note** : Le schéma de la base de données est créé automatiquement au premier démarrage.

### Déployer un agent

```bash
export MAPPER_BACKEND_URL="http://votre-serveur:8080"
export MAPPER_API_KEY="votre-api-key"  # Voir .env
./deploy-agent.sh 192.168.1.25 root
```

## Configuration

### Variables d'environnement principales

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MAPPER_DB_HOST` | Hôte PostgreSQL | `postgres` (container) |
| `MAPPER_DB_PORT` | Port PostgreSQL | `5432` |
| `MAPPER_DB_USER` | Utilisateur PostgreSQL | `postgres` |
| `MAPPER_DB_PASSWORD` | Mot de passe PostgreSQL | (requis) |
| `MAPPER_DB_NAME` | Nom de la base | `infra_mapper` |
| `MAPPER_API_KEY` | Clé API pour les agents | (requis) |
| `MAPPER_SECRET_KEY` | Clé secrète JWT | (requis) |
| `MAPPER_PORT` | Port d'exposition | `8080` |
| `MAPPER_AUTH_ENABLED` | Activer l'authentification | `true` |
| `MAPPER_BACKEND_URL` | URL accessible aux agents | (requis) |
| `MAPPER_INITIAL_ADMIN_PASSWORD` | Mot de passe admin initial | (optionnel) |

Voir [.env.example](.env.example) pour toutes les options.

### Configuration Tailscale

Si vos serveurs utilisent Tailscale, utilisez les IPs Tailscale pour la communication :

```env
# Backend accessible via Tailscale
MAPPER_BACKEND_URL=http://100.x.x.x:8080

# PostgreSQL sur un autre serveur Tailscale
MAPPER_DB_HOST=100.x.x.x
```

## Structure du projet

```
infra-mapper/
├── agent/                  # Agent Python (déployé sur chaque hôte)
│   ├── collectors/         # Modules: Docker, réseau, Tailscale, logs
│   ├── agent.py            # Point d'entrée
│   └── .env.example
├── backend/                # API FastAPI
│   ├── api/                # Routes REST et WebSocket
│   ├── db/                 # Modèles SQLAlchemy (auto-migration)
│   ├── services/           # Logique métier
│   ├── middleware/         # Sécurité, rate limiting, métriques
│   └── tests/
├── frontend/               # Interface Vue.js
│   ├── src/
│   │   ├── components/     # GraphView, NodeDetails, etc.
│   │   ├── views/          # Pages (Login, Inventory, Metrics, etc.)
│   │   ├── stores/         # État Pinia
│   │   └── composables/    # Logique Cytoscape
│   └── public/
├── scripts/                # Scripts utilitaires
├── ssh-keys/               # Clés SSH (gitignored)
├── docker-compose.yml      # Production avec DB externe
├── docker-compose.prod.yml # Production avec DB incluse
├── docker-compose.dev.yml  # Développement
├── deploy-agent.sh         # Script de déploiement agent
├── .env.example            # Template de configuration
├── QUICKSTART.md           # Guide de démarrage
└── README.md
```

## API REST

### Endpoints principaux

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/api/v1/report` | Reçoit un rapport d'agent |
| `GET` | `/api/v1/graph` | Données du graphe |
| `GET` | `/api/v1/hosts` | Liste des hôtes |
| `GET` | `/api/v1/hosts/{id}/containers` | Conteneurs d'un hôte |
| `GET` | `/api/v1/metrics/hosts` | Métriques de tous les hôtes |
| `GET` | `/api/v1/metrics/hosts/{id}` | Historique métriques d'un hôte |
| `GET` | `/api/v1/agents/health/summary` | Santé des agents |
| `GET` | `/api/v1/metrics/prometheus` | Export Prometheus |
| `GET` | `/api/v1/metrics/internal` | Métriques internes backend |
| `WS` | `/ws` | WebSocket temps réel |
| `GET` | `/health` | Health check |

### Authentification

```bash
# Login
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "xxx"}'

# Requête authentifiée (utilisateur)
curl http://localhost:8080/api/v1/hosts \
  -H "Authorization: Bearer <token>"

# Requête agent (API key)
curl -X POST http://localhost:8080/api/v1/report \
  -H "X-API-Key: <api-key>" \
  -H "Content-Type: application/json" \
  -d @report.json
```

## Interface

### Pages principales

- **Graphe** : Visualisation interactive de l'infrastructure
- **Inventaire** : Liste détaillée des hôtes et conteneurs
- **Logs** : Logs centralisés des conteneurs
- **Métriques** : Graphiques CPU/RAM/Disque/Réseau
- **Paramètres** : Configuration, utilisateurs, alertes, backups

### Légende du graphe

| Élément | Description |
|---------|-------------|
| 🟦 Rectangle | Hôte/VM |
| 🟢 Cercle vert | Conteneur actif |
| 🔴 Cercle rouge | Conteneur arrêté |
| 🟣 Losange | Service externe |
| ➡️ Ligne continue | Connexion réseau détectée |
| ⤏ Ligne pointillée | Dépendance docker-compose |

## Développement

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
pytest
pytest --cov=. --cov-report=html
```

## Production

### Recommandations

1. **HTTPS** : Utilisez un reverse proxy (Nginx Proxy Manager, Traefik)
2. **Secrets** : Générez des clés fortes (`openssl rand -hex 32`)
3. **Backup** : Sauvegardez la base PostgreSQL régulièrement
4. **Monitoring** : Intégrez l'endpoint Prometheus

### Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name infra.example.com;

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

## Intégrations

### Prometheus

```yaml
scrape_configs:
  - job_name: 'infra-mapper'
    static_configs:
      - targets: ['infra-mapper:8080']
    metrics_path: '/api/v1/metrics/prometheus'
```

### Alertes

Canaux supportés : Slack, Discord, Telegram, Email, ntfy, Webhook générique.

Configuration dans **Paramètres > Alertes**.

## Dépannage

### L'agent ne se connecte pas

```bash
# Vérifier la connectivité
curl http://votre-serveur:8080/health

# Vérifier l'API key
curl -H "X-API-Key: votre-api-key" http://votre-serveur:8080/api/v1/hosts

# Logs de l'agent
docker logs infra-mapper-agent
```

### Agent en état "Degraded"

- Augmenter `MAPPER_SCAN_INTERVAL` (90s recommandé avec tcpdump)
- Vérifier les ressources du serveur

### Base de données inaccessible

- Vérifier la connectivité réseau (firewall, Tailscale)
- Vérifier les credentials dans `.env`
- PostgreSQL doit écouter sur l'interface externe

## Licence

MIT License - voir [LICENSE](LICENSE)

## Contribuer

Les contributions sont les bienvenues !

1. Fork le projet
2. Créez une branche (`git checkout -b feature/amazing-feature`)
3. Committez vos changements (`git commit -m 'Add amazing feature'`)
4. Push sur la branche (`git push origin feature/amazing-feature`)
5. Ouvrez une Pull Request
