"""Modèles SQLAlchemy pour la base de données."""

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from .database import Base

# Import des modèles auth pour qu'ils soient créés avec les autres tables
from .auth_models import (
    User,
    UserSession,
    IdentityProvider,
    AuditLog,
    RoleEnum,
    IdentityProviderType,
    AuditActionType,
)


class ContainerStatusEnum(str, enum.Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESTARTING = "restarting"
    EXITED = "exited"
    DEAD = "dead"
    CREATED = "created"
    UNKNOWN = "unknown"


class HealthStatusEnum(str, enum.Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    NONE = "none"


class VmStatusEnum(str, enum.Enum):
    """Statut d'une VM managée."""
    PENDING = "pending"      # En attente de premier contact
    ONLINE = "online"        # Agent actif
    OFFLINE = "offline"      # Agent non répondant
    DEPLOYING = "deploying"  # Déploiement en cours
    ERROR = "error"          # Erreur


class OsTypeEnum(str, enum.Enum):
    """Type de système d'exploitation."""
    DEBIAN = "debian"
    CENTOS = "centos"
    UBUNTU = "ubuntu"
    MACOS = "macos"
    WINDOWS = "windows"
    UNKNOWN = "unknown"


class AgentHealthStatus(str, enum.Enum):
    """Statut de santé de l'agent."""
    HEALTHY = "healthy"       # Agent fonctionne normalement
    DEGRADED = "degraded"     # Agent répond mais avec retard ou erreurs partielles
    UNHEALTHY = "unhealthy"   # Agent ne répond plus
    UNKNOWN = "unknown"       # Pas encore de données suffisantes


class Host(Base):
    """Table des hôtes (VMs/machines)."""

    __tablename__ = "hosts"

    id = Column(String, primary_key=True)  # agent_id
    hostname = Column(String, nullable=False, index=True)
    ip_addresses = Column(JSON, default=list)  # Liste des IPs
    tailscale_ip = Column(String, nullable=True)
    tailscale_hostname = Column(String, nullable=True)
    docker_version = Column(String, nullable=True)
    os_info = Column(String, nullable=True)

    # Métadonnées
    first_seen = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now())
    is_online = Column(Boolean, default=True)

    # === Agent Monitoring ===
    agent_version = Column(String, nullable=True)  # Version de l'agent (ex: "1.2.3")
    agent_health = Column(String, default="unknown")  # healthy, degraded, unhealthy, unknown

    # Timing du rapport
    report_interval = Column(Integer, nullable=True)  # Intervalle configuré en secondes
    last_report_duration = Column(Integer, nullable=True)  # Durée du dernier rapport en ms
    avg_report_duration = Column(Integer, nullable=True)  # Durée moyenne des rapports en ms

    # Détection de dégradation
    consecutive_failures = Column(Integer, default=0)  # Compteur d'échecs consécutifs
    last_error = Column(String, nullable=True)  # Dernière erreur rapportée
    last_error_at = Column(DateTime, nullable=True)  # Date de la dernière erreur

    # Statistiques agent
    reports_count = Column(Integer, default=0)  # Nombre total de rapports reçus
    errors_count = Column(Integer, default=0)  # Nombre total d'erreurs
    uptime_seconds = Column(Integer, nullable=True)  # Uptime de l'agent depuis démarrage

    # Command server
    command_port = Column(Integer, nullable=True)  # Port du serveur de commandes (si actif)

    # Relations
    containers = relationship("Container", back_populates="host", cascade="all, delete-orphan")
    networks = relationship("Network", back_populates="host", cascade="all, delete-orphan")

    # Index
    __table_args__ = (
        Index("ix_hosts_last_seen", "last_seen"),
        Index("ix_hosts_agent_health", "agent_health"),
    )


class Container(Base):
    """Table des conteneurs."""

    __tablename__ = "containers"

    id = Column(String, primary_key=True)  # host_id + container_id
    container_id = Column(String, nullable=False)  # ID court Docker
    host_id = Column(String, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False, index=True)
    image = Column(String, nullable=False)

    # Statut
    status = Column(SQLEnum(ContainerStatusEnum), default=ContainerStatusEnum.UNKNOWN)
    health = Column(SQLEnum(HealthStatusEnum), default=HealthStatusEnum.NONE)

    # Réseau
    networks = Column(JSON, default=list)  # Liste des noms de réseaux
    ip_addresses = Column(JSON, default=dict)  # {network: ip}
    ports = Column(JSON, default=list)  # Liste des PortMapping

    # Compose
    compose_project = Column(String, nullable=True, index=True)
    compose_service = Column(String, nullable=True)
    declared_dependencies = Column(JSON, default=list)

    # Volumes
    volumes = Column(JSON, default=list)

    # Labels et environnement
    labels = Column(JSON, default=dict)
    environment = Column(JSON, default=dict)

    # Métadonnées
    created_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    first_seen = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relations
    host = relationship("Host", back_populates="containers")

    # Index
    __table_args__ = (
        Index("ix_containers_host_status", "host_id", "status"),
        Index("ix_containers_compose", "compose_project", "compose_service"),
    )


class Network(Base):
    """Table des réseaux Docker."""

    __tablename__ = "networks"

    id = Column(String, primary_key=True)  # host_id + network_id
    network_id = Column(String, nullable=False)
    host_id = Column(String, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    driver = Column(String, default="bridge")
    scope = Column(String, default="local")
    subnet = Column(String, nullable=True)
    gateway = Column(String, nullable=True)
    containers = Column(JSON, default=list)  # Liste des IDs de conteneurs

    # Métadonnées
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relations
    host = relationship("Host", back_populates="networks")


class Connection(Base):
    """Table des connexions réseau détectées."""

    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Source
    source_host_id = Column(String, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    source_container_id = Column(String, nullable=True)  # Peut être null si c'est l'hôte
    source_ip = Column(String, nullable=False)
    source_port = Column(Integer, nullable=False)

    # Destination
    target_host_id = Column(String, nullable=True)  # Peut être null si externe
    target_container_id = Column(String, nullable=True)
    target_ip = Column(String, nullable=False)
    target_port = Column(Integer, nullable=False)

    # Métadonnées
    protocol = Column(String, default="tcp")
    state = Column(String, default="ESTABLISHED")
    connection_type = Column(String, default="unknown")  # internal, cross-host, external
    source_method = Column(String, default="proc_net")  # proc_net, tcpdump

    # Timestamps
    first_seen = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now())

    # Index
    __table_args__ = (
        Index("ix_connections_source", "source_host_id", "source_container_id"),
        Index("ix_connections_target", "target_host_id", "target_container_id"),
        Index("ix_connections_type", "connection_type"),
    )


class Dashboard(Base):
    """Table des dashboards personnalisés."""

    __tablename__ = "dashboards"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # Filtres du dashboard
    host_filter = Column(String, nullable=True)  # Pattern pour filtrer les hôtes
    project_filter = Column(String, nullable=True)  # Pattern pour filtrer les projets
    include_offline = Column(Boolean, default=True)

    # Options d'affichage
    show_external = Column(Boolean, default=True)
    edge_filters = Column(JSON, default=dict)  # Copie des filtres d'edges

    # Métadonnées
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relations
    nodes = relationship("DashboardNode", back_populates="dashboard", cascade="all, delete-orphan")


class DashboardNode(Base):
    """Table des positions de nœuds dans un dashboard."""

    __tablename__ = "dashboard_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dashboard_id = Column(String, ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False)

    # Référence au nœud (container ou external)
    node_id = Column(String, nullable=False)  # Ex: "container:host_id:container_id"
    node_type = Column(String, nullable=False)  # container, external

    # Position sauvegardée
    position_x = Column(Integer, nullable=False, default=0)
    position_y = Column(Integer, nullable=False, default=0)

    # Pour les nœuds disparus - on garde la position pendant 7 jours
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now())
    is_visible = Column(Boolean, default=True)  # False si le conteneur a disparu

    # Relations
    dashboard = relationship("Dashboard", back_populates="nodes")

    # Index
    __table_args__ = (
        Index("ix_dashboard_nodes_dashboard", "dashboard_id"),
        Index("ix_dashboard_nodes_node", "node_id"),
        Index("ix_dashboard_nodes_last_seen", "last_seen"),
    )


class Vm(Base):
    """Table des VMs managées (manuelles ou auto-découvertes)."""

    __tablename__ = "vms"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False)
    hostname = Column(String, nullable=False, index=True)
    ip_address = Column(String, nullable=False)
    ssh_port = Column(Integer, default=22)
    ssh_user = Column(String, default="root")
    os_type = Column(SQLEnum(OsTypeEnum), default=OsTypeEnum.UNKNOWN)
    status = Column(SQLEnum(VmStatusEnum), default=VmStatusEnum.PENDING)

    # Lien optionnel vers l'hôte découvert (quand agent connecté)
    host_id = Column(String, ForeignKey("hosts.id", ondelete="SET NULL"), nullable=True)

    # Agent info
    agent_version = Column(String, nullable=True)
    agent_installed_at = Column(DateTime, nullable=True)

    # Deployment progress tracking
    deployment_step = Column(String, nullable=True)  # "uploading", "building", "starting", etc.
    deployment_progress = Column(Integer, nullable=True)  # 0-100
    deployment_message = Column(String, nullable=True)  # Detailed message or error

    # Auto-découverte vs manuel
    is_auto_discovered = Column(Boolean, default=False)

    # Métadonnées
    tags = Column(JSON, default=list)  # ["production", "database"]
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Index
    __table_args__ = (
        Index("ix_vms_status", "status"),
        Index("ix_vms_host_id", "host_id"),
    )


class ContainerLog(Base):
    """Table des logs de containers collectés."""

    __tablename__ = "container_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    container_id = Column(String, nullable=False)  # Format: host_id:container_id
    host_id = Column(String, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)

    timestamp = Column(DateTime, nullable=False, index=True)
    stream = Column(String, default="stdout")  # stdout, stderr
    message = Column(String, nullable=False)

    # Index pour pagination efficace
    __table_args__ = (
        Index("ix_container_logs_container_time", "container_id", "timestamp"),
        Index("ix_container_logs_host_time", "host_id", "timestamp"),
    )


# =============================================================================
# METRICS SYSTEM (Time-Series)
# =============================================================================

class HostMetrics(Base):
    """Métriques time-series pour les hosts (CPU, RAM, disque)."""

    __tablename__ = "host_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    host_id = Column(String, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)

    # CPU
    cpu_percent = Column(Integer, nullable=True)  # 0-100
    cpu_count = Column(Integer, nullable=True)
    load_1m = Column(Integer, nullable=True)  # Load average * 100
    load_5m = Column(Integer, nullable=True)
    load_15m = Column(Integer, nullable=True)

    # Mémoire (en MB)
    memory_total = Column(Integer, nullable=True)
    memory_used = Column(Integer, nullable=True)
    memory_percent = Column(Integer, nullable=True)  # 0-100

    # Disque (en MB)
    disk_total = Column(Integer, nullable=True)
    disk_used = Column(Integer, nullable=True)
    disk_percent = Column(Integer, nullable=True)  # 0-100

    # Réseau (en bytes depuis démarrage)
    network_rx_bytes = Column(BigInteger, nullable=True)
    network_tx_bytes = Column(BigInteger, nullable=True)

    # Index pour requêtes time-series
    __table_args__ = (
        Index("ix_host_metrics_host_time", "host_id", "timestamp"),
        Index("ix_host_metrics_time", "timestamp"),
    )


class ContainerMetrics(Base):
    """Métriques time-series pour les containers."""

    __tablename__ = "container_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    container_id = Column(String, nullable=False)  # Format: host_id:container_short_id
    host_id = Column(String, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)

    # CPU
    cpu_percent = Column(Integer, nullable=True)  # 0-10000 (100.00% * 100)

    # Mémoire (en MB)
    memory_used = Column(Integer, nullable=True)
    memory_limit = Column(Integer, nullable=True)
    memory_percent = Column(Integer, nullable=True)  # 0-100

    # Réseau (en bytes depuis démarrage)
    network_rx_bytes = Column(BigInteger, nullable=True)
    network_tx_bytes = Column(BigInteger, nullable=True)

    # Disque I/O (en bytes)
    disk_read_bytes = Column(BigInteger, nullable=True)
    disk_write_bytes = Column(BigInteger, nullable=True)

    # PIDs
    pids = Column(Integer, nullable=True)

    # Index pour requêtes time-series
    __table_args__ = (
        Index("ix_container_metrics_container_time", "container_id", "timestamp"),
        Index("ix_container_metrics_host_time", "host_id", "timestamp"),
        Index("ix_container_metrics_time", "timestamp"),
    )


# =============================================================================
# LOG FORWARDING SYSTEM
# =============================================================================

class LogSinkType(str, enum.Enum):
    """Types de puits de logs externes."""
    GRAYLOG = "graylog"           # Graylog GELF
    OPENOBSERVE = "openobserve"   # OpenObserve HTTP
    LOKI = "loki"                 # Grafana Loki
    ELASTICSEARCH = "elasticsearch"  # Elasticsearch
    SPLUNK = "splunk"             # Splunk HEC
    SYSLOG = "syslog"             # Syslog (TCP/UDP)
    WEBHOOK = "webhook"           # Generic HTTP webhook


class LogSink(Base):
    """Configuration d'un puits de logs externe."""

    __tablename__ = "log_sinks"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    type = Column(SQLEnum(LogSinkType), nullable=False)
    enabled = Column(Boolean, default=True)

    # Configuration commune
    url = Column(String, nullable=False)  # URL/endpoint
    port = Column(Integer, nullable=True)  # Port (optionnel si dans URL)

    # Authentification
    auth_type = Column(String, nullable=True)  # none, basic, token, api_key
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)  # Chiffre en prod
    api_key = Column(String, nullable=True)
    token = Column(String, nullable=True)

    # Configuration specifique (JSON flexible)
    config = Column(JSON, default=dict)
    # Exemples de config:
    # Graylog: {"facility": "infra-mapper", "version": "1.1"}
    # Loki: {"tenant_id": "default", "labels": {"app": "infra-mapper"}}
    # Syslog: {"protocol": "tcp", "facility": 1, "severity": 6}
    # OpenObserve: {"org": "default", "stream": "logs"}

    # Filtres
    filter_hosts = Column(JSON, default=list)  # [] = tous, sinon liste host_ids
    filter_containers = Column(JSON, default=list)  # [] = tous
    filter_streams = Column(JSON, default=list)  # [] = tous, ["stderr"], ["stdout", "stderr"]

    # TLS/SSL
    tls_enabled = Column(Boolean, default=False)
    tls_verify = Column(Boolean, default=True)
    tls_ca_cert = Column(String, nullable=True)

    # Rate limiting / batching
    batch_size = Column(Integer, default=100)
    flush_interval = Column(Integer, default=5)  # secondes

    # Statistiques
    last_success = Column(DateTime, nullable=True)
    last_error = Column(DateTime, nullable=True)
    last_error_message = Column(String, nullable=True)
    logs_sent = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# =============================================================================
# ALERTING SYSTEM
# =============================================================================

class AlertChannelType(str, enum.Enum):
    """Types de canaux de notification."""
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    EMAIL = "email"
    NTFY = "ntfy"
    WEBHOOK = "webhook"


class AlertRuleType(str, enum.Enum):
    """Types de règles d'alerte."""
    HOST_OFFLINE = "host_offline"           # Host non vu depuis X minutes
    CONTAINER_STOPPED = "container_stopped"  # Container arrêté
    CONTAINER_UNHEALTHY = "container_unhealthy"  # Container unhealthy
    CONTAINER_RESTARTING = "container_restarting"  # Container qui redémarre souvent
    HIGH_RESTART_COUNT = "high_restart_count"  # Nombre de redémarrages élevé
    NEW_CONTAINER = "new_container"          # Nouveau container détecté
    CONTAINER_REMOVED = "container_removed"   # Container supprimé


class AlertSeverity(str, enum.Enum):
    """Niveaux de sévérité des alertes."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    """Statut d'une alerte."""
    ACTIVE = "active"       # Alerte en cours
    RESOLVED = "resolved"   # Alerte résolue automatiquement
    ACKNOWLEDGED = "acknowledged"  # Alerte acquittée manuellement


class AlertChannel(Base):
    """Table des canaux de notification."""

    __tablename__ = "alert_channels"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False)
    channel_type = Column(SQLEnum(AlertChannelType), nullable=False)
    enabled = Column(Boolean, default=True)

    # Configuration spécifique au canal (webhook_url, token, etc.)
    config = Column(JSON, default=dict)
    # Exemple config:
    # slack: {"webhook_url": "https://hooks.slack.com/..."}
    # discord: {"webhook_url": "https://discord.com/api/webhooks/..."}
    # telegram: {"bot_token": "...", "chat_id": "..."}
    # email: {"smtp_host": "...", "smtp_port": 587, "from": "...", "to": ["..."]}
    # ntfy: {"server": "https://ntfy.sh", "topic": "..."}
    # webhook: {"url": "...", "method": "POST", "headers": {...}}

    # Filtres (optionnels)
    severity_filter = Column(JSON, default=list)  # ["warning", "critical"] - vide = tout
    rule_type_filter = Column(JSON, default=list)  # ["host_offline"] - vide = tout

    # Métadonnées
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_used_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)

    # Index
    __table_args__ = (
        Index("ix_alert_channels_type", "channel_type"),
        Index("ix_alert_channels_enabled", "enabled"),
    )


class AlertRule(Base):
    """Table des règles d'alerte."""

    __tablename__ = "alert_rules"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    rule_type = Column(SQLEnum(AlertRuleType), nullable=False)
    severity = Column(SQLEnum(AlertSeverity), default=AlertSeverity.WARNING)
    enabled = Column(Boolean, default=True)

    # Configuration de la règle
    config = Column(JSON, default=dict)
    # Exemples:
    # host_offline: {"timeout_minutes": 5}
    # container_stopped: {"container_filter": "prod-*", "exclude": ["backup-*"]}
    # container_unhealthy: {"container_filter": "*"}
    # high_restart_count: {"threshold": 3, "period_minutes": 60}

    # Filtres de scope
    host_filter = Column(String, nullable=True)  # Pattern regex pour hosts
    container_filter = Column(String, nullable=True)  # Pattern regex pour containers
    project_filter = Column(String, nullable=True)  # Pattern pour projets compose

    # Cooldown pour éviter le spam
    cooldown_minutes = Column(Integer, default=15)  # Temps minimum entre 2 alertes identiques

    # Métadonnées
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relations
    alerts = relationship("Alert", back_populates="rule", cascade="all, delete-orphan")

    # Index
    __table_args__ = (
        Index("ix_alert_rules_type", "rule_type"),
        Index("ix_alert_rules_enabled", "enabled"),
    )


class Alert(Base):
    """Table des alertes générées."""

    __tablename__ = "alerts"

    id = Column(String, primary_key=True)  # UUID
    rule_id = Column(String, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False)

    # Informations sur l'alerte
    severity = Column(SQLEnum(AlertSeverity), nullable=False)
    status = Column(SQLEnum(AlertStatus), default=AlertStatus.ACTIVE)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)

    # Contexte
    host_id = Column(String, nullable=True)  # Host concerné
    host_name = Column(String, nullable=True)
    container_id = Column(String, nullable=True)  # Container concerné
    container_name = Column(String, nullable=True)

    # Données additionnelles
    context = Column(JSON, default=dict)  # Données supplémentaires

    # Timestamps
    triggered_at = Column(DateTime, default=func.now())
    resolved_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String, nullable=True)  # User ID

    # Notification tracking
    notifications_sent = Column(JSON, default=list)  # [{"channel_id": "...", "sent_at": "...", "success": true}]

    # Relations
    rule = relationship("AlertRule", back_populates="alerts")

    # Index
    __table_args__ = (
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_triggered", "triggered_at"),
        Index("ix_alerts_rule", "rule_id"),
        Index("ix_alerts_host", "host_id"),
        Index("ix_alerts_container", "container_id"),
    )


# =============================================================================
# SCHEDULED REPORTS SYSTEM
# =============================================================================

class ReportFrequency(str, enum.Enum):
    """Fréquence des rapports planifiés."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReportFormat(str, enum.Enum):
    """Format des rapports."""
    JSON = "json"
    CSV = "csv"
    HTML = "html"


class ReportType(str, enum.Enum):
    """Types de rapports."""
    INVENTORY = "inventory"              # Liste des hosts/containers
    CONNECTIONS = "connections"          # Carte des connexions
    SUMMARY = "summary"                  # Résumé statistique
    CHANGES = "changes"                  # Changements depuis dernier rapport
    HEALTH = "health"                    # État de santé global


class ScheduledReport(Base):
    """Table des rapports planifiés."""

    __tablename__ = "scheduled_reports"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    enabled = Column(Boolean, default=True)

    # Type et format
    report_type = Column(SQLEnum(ReportType), nullable=False)
    report_format = Column(SQLEnum(ReportFormat), default=ReportFormat.JSON)

    # Planification
    frequency = Column(SQLEnum(ReportFrequency), nullable=False)
    schedule_hour = Column(Integer, default=8)  # Heure d'exécution (0-23)
    schedule_day = Column(Integer, nullable=True)  # Jour de la semaine (0-6) ou du mois (1-31)

    # Filtres (optionnels)
    host_filter = Column(String, nullable=True)
    project_filter = Column(String, nullable=True)
    include_offline = Column(Boolean, default=True)

    # Destination
    destination_type = Column(String, default="email")  # email, webhook, storage
    destination_config = Column(JSON, default=dict)
    # email: {"recipients": ["admin@example.com"], "subject_prefix": "[Infra-Mapper]"}
    # webhook: {"url": "https://...", "method": "POST", "headers": {...}}
    # storage: {"path": "/reports/", "retention_days": 30}

    # Exécution
    last_run_at = Column(DateTime, nullable=True)
    last_run_status = Column(String, nullable=True)  # success, error
    last_run_error = Column(String, nullable=True)
    next_run_at = Column(DateTime, nullable=True)

    # Statistiques
    runs_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)

    # Métadonnées
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Index
    __table_args__ = (
        Index("ix_scheduled_reports_enabled", "enabled"),
        Index("ix_scheduled_reports_next_run", "next_run_at"),
    )


class ReportHistory(Base):
    """Historique des rapports générés."""

    __tablename__ = "report_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String, ForeignKey("scheduled_reports.id", ondelete="CASCADE"), nullable=False)

    # Exécution
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")  # running, success, error
    error_message = Column(String, nullable=True)

    # Résultat
    file_path = Column(String, nullable=True)  # Chemin si stocké localement
    file_size = Column(Integer, nullable=True)  # Taille en bytes

    # Statistiques du rapport
    stats = Column(JSON, default=dict)
    # Ex: {"hosts": 5, "containers": 42, "connections": 128}

    # Index
    __table_args__ = (
        Index("ix_report_history_report", "report_id"),
        Index("ix_report_history_started", "started_at"),
    )
