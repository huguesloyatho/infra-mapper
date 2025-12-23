"""Schémas Pydantic pour l'API."""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from enum import Enum


# === Enums ===

class ContainerStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESTARTING = "restarting"
    EXITED = "exited"
    DEAD = "dead"
    CREATED = "created"
    UNKNOWN = "unknown"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    NONE = "none"


class VmStatus(str, Enum):
    """Statut d'une VM managée."""
    PENDING = "pending"
    ONLINE = "online"
    OFFLINE = "offline"
    DEPLOYING = "deploying"
    ERROR = "error"


class OsType(str, Enum):
    """Type de système d'exploitation."""
    DEBIAN = "debian"
    CENTOS = "centos"
    UBUNTU = "ubuntu"
    MACOS = "macos"
    WINDOWS = "windows"
    UNKNOWN = "unknown"


# === Modèles de base (depuis l'agent) ===

class PortMapping(BaseModel):
    container_port: int
    host_port: Optional[int] = None
    protocol: str = "tcp"
    host_ip: str = "0.0.0.0"


class VolumeMount(BaseModel):
    source: str
    destination: str
    mode: str = "rw"
    type: str = "bind"


class NetworkConnection(BaseModel):
    protocol: str
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    state: str
    pid: Optional[int] = None
    process_name: Optional[str] = None
    container_id: Optional[str] = None
    source_method: str = "proc_net"  # proc_net, tcpdump


class ContainerInfo(BaseModel):
    id: str
    name: str
    image: str
    status: ContainerStatus
    health: HealthStatus = HealthStatus.NONE
    created: datetime
    started_at: Optional[datetime] = None
    networks: list[str] = Field(default_factory=list)
    ip_addresses: dict[str, str] = Field(default_factory=dict)
    ports: list[PortMapping] = Field(default_factory=list)
    volumes: list[VolumeMount] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)
    compose_project: Optional[str] = None
    compose_service: Optional[str] = None
    declared_dependencies: list[str] = Field(default_factory=list)


class NetworkInfo(BaseModel):
    id: str
    name: str
    driver: str
    scope: str
    subnet: Optional[str] = None
    gateway: Optional[str] = None
    containers: list[str] = Field(default_factory=list)


class TailscaleInfo(BaseModel):
    enabled: bool = False
    ip: Optional[str] = None
    hostname: Optional[str] = None
    tailnet: Optional[str] = None
    peers: dict[str, str] = Field(default_factory=dict)


class AgentMetadata(BaseModel):
    """Métadonnées de l'agent pour le monitoring."""
    version: Optional[str] = None  # Version de l'agent (ex: "1.2.3")
    report_interval: Optional[int] = None  # Intervalle de rapport configuré en secondes
    report_duration_ms: Optional[int] = None  # Durée de génération du rapport en ms
    uptime_seconds: Optional[int] = None  # Uptime de l'agent depuis démarrage
    error: Optional[str] = None  # Message d'erreur si le rapport contient une erreur
    command_port: Optional[int] = None  # Port du serveur de commandes (si actif)


class HostInfo(BaseModel):
    agent_id: str
    hostname: str
    ip_addresses: list[str] = Field(default_factory=list)
    tailscale: Optional[TailscaleInfo] = None
    os_info: Optional[str] = None
    docker_version: Optional[str] = None


class ContainerLogReport(BaseModel):
    """Log de container dans le rapport agent."""
    container_id: str
    timestamp: str
    message: str
    stream: str = "stdout"


class HostMetricsReport(BaseModel):
    """Métriques système du host dans le rapport agent."""
    cpu_percent: Optional[float] = None
    cpu_count: Optional[int] = None
    load_1m: Optional[float] = None
    load_5m: Optional[float] = None
    load_15m: Optional[float] = None
    memory_total: Optional[int] = None  # MB
    memory_used: Optional[int] = None   # MB
    memory_percent: Optional[float] = None
    disk_total: Optional[int] = None    # MB
    disk_used: Optional[int] = None     # MB
    disk_percent: Optional[float] = None
    network_rx_bytes: Optional[int] = None
    network_tx_bytes: Optional[int] = None


class ContainerMetricsReport(BaseModel):
    """Métriques d'un container dans le rapport agent."""
    container_id: str
    cpu_percent: Optional[float] = None
    memory_used: Optional[int] = None   # MB
    memory_limit: Optional[int] = None  # MB
    memory_percent: Optional[float] = None
    network_rx_bytes: Optional[int] = None
    network_tx_bytes: Optional[int] = None
    disk_read_bytes: Optional[int] = None
    disk_write_bytes: Optional[int] = None
    pids: Optional[int] = None


class AgentReport(BaseModel):
    host: HostInfo
    containers: list[ContainerInfo] = Field(default_factory=list)
    networks: list[NetworkInfo] = Field(default_factory=list)
    connections: list[NetworkConnection] = Field(default_factory=list)
    container_logs: list[ContainerLogReport] = Field(default_factory=list)
    host_metrics: Optional[HostMetricsReport] = None
    container_metrics: list[ContainerMetricsReport] = Field(default_factory=list)
    agent: Optional[AgentMetadata] = None  # Métadonnées de l'agent pour le monitoring
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# === Modèles de réponse API ===

class HostResponse(BaseModel):
    agent_id: str
    hostname: str
    ip_addresses: list[str]
    tailscale_ip: Optional[str] = None
    docker_version: Optional[str] = None
    container_count: int = 0
    last_seen: datetime
    status: Literal["online", "offline", "unknown"] = "unknown"


class ContainerResponse(BaseModel):
    id: str
    name: str
    host_id: str
    host_name: str
    image: str
    status: ContainerStatus
    health: HealthStatus
    ports: list[PortMapping]
    compose_project: Optional[str] = None
    compose_service: Optional[str] = None
    last_seen: datetime


class ConnectionResponse(BaseModel):
    source_container_id: Optional[str]
    source_container_name: Optional[str]
    source_host_id: str
    source_ip: str
    source_port: int
    target_container_id: Optional[str]
    target_container_name: Optional[str]
    target_host_id: Optional[str]
    target_ip: str
    target_port: int
    protocol: str
    connection_type: Literal["internal", "cross-host", "external"]


# === Modèles pour le graphe ===

class GraphNode(BaseModel):
    id: str
    label: str
    type: Literal["host", "container", "external"]
    parent: Optional[str] = None  # ID du host pour les containers
    data: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: Optional[str] = None
    type: Literal["network", "dependency", "connection"]
    data: dict = Field(default_factory=dict)


class GraphData(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# === Modèles pour les dashboards personnalisés ===

class NodePosition(BaseModel):
    """Position d'un nœud dans le dashboard."""
    node_id: str
    x: float
    y: float


class DashboardNodeResponse(BaseModel):
    """Nœud avec sa position sauvegardée."""
    node_id: str
    node_type: str
    position_x: float
    position_y: float
    is_visible: bool = True
    last_seen: datetime


class EdgeFilters(BaseModel):
    """Filtres de visibilité des edges."""
    show_internal: bool = True
    show_cross_host: bool = True
    show_external: bool = True
    show_proc_net: bool = True
    show_tcpdump: bool = True
    show_connections: bool = True
    show_dependencies: bool = True


class DashboardCreate(BaseModel):
    """Création d'un dashboard."""
    name: str
    description: Optional[str] = None
    host_filter: Optional[str] = None
    project_filter: Optional[str] = None
    include_offline: bool = True
    show_external: bool = True
    edge_filters: EdgeFilters = Field(default_factory=EdgeFilters)


class DashboardUpdate(BaseModel):
    """Mise à jour d'un dashboard."""
    name: Optional[str] = None
    description: Optional[str] = None
    host_filter: Optional[str] = None
    project_filter: Optional[str] = None
    include_offline: Optional[bool] = None
    show_external: Optional[bool] = None
    edge_filters: Optional[EdgeFilters] = None


class DashboardResponse(BaseModel):
    """Réponse complète d'un dashboard."""
    id: str
    name: str
    description: Optional[str] = None
    host_filter: Optional[str] = None
    project_filter: Optional[str] = None
    include_offline: bool = True
    show_external: bool = True
    edge_filters: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    node_count: int = 0


class DashboardWithPositions(BaseModel):
    """Dashboard avec les positions des nœuds."""
    dashboard: DashboardResponse
    positions: dict[str, NodePosition] = Field(default_factory=dict)  # node_id -> position


class SavePositionsRequest(BaseModel):
    """Requête pour sauvegarder les positions."""
    positions: list[NodePosition]


# === Modèles pour la gestion des VMs ===

class VmCreate(BaseModel):
    """Création d'une VM."""
    name: str
    hostname: str
    ip_address: str
    ssh_port: int = 22
    ssh_user: str = "root"
    os_type: OsType = OsType.UNKNOWN
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class VmUpdate(BaseModel):
    """Mise à jour d'une VM."""
    name: Optional[str] = None
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: Optional[str] = None
    os_type: Optional[OsType] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    is_auto_discovered: Optional[bool] = None


class VmResponse(BaseModel):
    """Réponse complète d'une VM."""
    id: str
    name: str
    hostname: str
    ip_address: str
    ssh_port: int
    ssh_user: str
    os_type: str
    status: str
    host_id: Optional[str] = None
    agent_version: Optional[str] = None
    agent_installed_at: Optional[datetime] = None
    is_auto_discovered: bool
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# === Modèles pour les actions agents ===

class AgentDeployRequest(BaseModel):
    """Requête de déploiement d'agents."""
    vm_ids: list[str]


class AgentActionRequest(BaseModel):
    """Requête d'action sur agents."""
    vm_ids: list[str]
    action: Literal["start", "stop", "restart", "update", "delete"]


class AgentLogsRequest(BaseModel):
    """Requête de logs agent."""
    vm_id: str
    lines: int = 100


class AgentLogsResponse(BaseModel):
    """Réponse logs agent."""
    vm_id: str
    logs: str


class SshTestRequest(BaseModel):
    """Requête de test de connexion SSH."""
    ip_address: str
    ssh_port: int = 22
    ssh_user: str = "root"


class SshTestResponse(BaseModel):
    """Réponse de test SSH."""
    success: bool
    message: str
    os_detected: Optional[str] = None


# === Modèles pour les logs de containers ===

class ContainerLogEntry(BaseModel):
    """Entrée de log d'un container."""
    timestamp: datetime
    stream: str  # stdout, stderr
    message: str


class ContainerLogsResponse(BaseModel):
    """Réponse des logs d'un container."""
    container_id: str
    container_name: str
    host_name: str
    logs: list[ContainerLogEntry] = Field(default_factory=list)
    total: int = 0


# === Modèles pour le système d'alerting ===

class AlertChannelType(str, Enum):
    """Types de canaux de notification."""
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    EMAIL = "email"
    NTFY = "ntfy"
    WEBHOOK = "webhook"


class AlertRuleType(str, Enum):
    """Types de règles d'alerte."""
    HOST_OFFLINE = "host_offline"
    CONTAINER_STOPPED = "container_stopped"
    CONTAINER_UNHEALTHY = "container_unhealthy"
    CONTAINER_RESTARTING = "container_restarting"
    HIGH_RESTART_COUNT = "high_restart_count"
    NEW_CONTAINER = "new_container"
    CONTAINER_REMOVED = "container_removed"


class AlertSeverity(str, Enum):
    """Niveaux de sévérité des alertes."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Statut d'une alerte."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


# -- AlertChannel --

class AlertChannelCreate(BaseModel):
    """Création d'un canal de notification."""
    name: str
    channel_type: AlertChannelType
    enabled: bool = True
    config: dict = Field(default_factory=dict)
    severity_filter: list[str] = Field(default_factory=list)
    rule_type_filter: list[str] = Field(default_factory=list)


class AlertChannelUpdate(BaseModel):
    """Mise à jour d'un canal."""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    severity_filter: Optional[list[str]] = None
    rule_type_filter: Optional[list[str]] = None


class AlertChannelResponse(BaseModel):
    """Réponse d'un canal."""
    id: str
    name: str
    channel_type: str
    enabled: bool
    config: dict
    severity_filter: list[str]
    rule_type_filter: list[str]
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None
    last_error: Optional[str] = None


# -- AlertRule --

class AlertRuleCreate(BaseModel):
    """Création d'une règle d'alerte."""
    name: str
    description: Optional[str] = None
    rule_type: AlertRuleType
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True
    config: dict = Field(default_factory=dict)
    host_filter: Optional[str] = None
    container_filter: Optional[str] = None
    project_filter: Optional[str] = None
    cooldown_minutes: int = 15


class AlertRuleUpdate(BaseModel):
    """Mise à jour d'une règle."""
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[AlertSeverity] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None
    host_filter: Optional[str] = None
    container_filter: Optional[str] = None
    project_filter: Optional[str] = None
    cooldown_minutes: Optional[int] = None


class AlertRuleResponse(BaseModel):
    """Réponse d'une règle."""
    id: str
    name: str
    description: Optional[str]
    rule_type: str
    severity: str
    enabled: bool
    config: dict
    host_filter: Optional[str]
    container_filter: Optional[str]
    project_filter: Optional[str]
    cooldown_minutes: int
    created_at: datetime
    updated_at: datetime


# -- Alert --

class AlertResponse(BaseModel):
    """Réponse d'une alerte."""
    id: str
    rule_id: str
    severity: str
    status: str
    title: str
    message: str
    host_id: Optional[str]
    host_name: Optional[str]
    container_id: Optional[str]
    container_name: Optional[str]
    context: dict
    triggered_at: datetime
    resolved_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    acknowledged_by: Optional[str]
    notifications_sent: list[dict]


class AlertsCountResponse(BaseModel):
    """Comptage des alertes actives."""
    total: int
    info: int
    warning: int
    critical: int


# === Modèles pour les actions sur containers ===

class ContainerActionRequest(BaseModel):
    """Requête d'action sur un container."""
    container_id: str
    timeout: int = 10


class ContainerExecRequest(BaseModel):
    """Requête d'exécution de commande dans un container."""
    command: str
    timeout: int = 30
    workdir: Optional[str] = None


class ContainerExecResponse(BaseModel):
    """Réponse d'exécution de commande."""
    success: bool
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None


class ContainerActionResponse(BaseModel):
    """Réponse d'action sur container."""
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


class ContainerStatsResponse(BaseModel):
    """Statistiques d'un container."""
    success: bool
    stats: Optional[dict] = None
    error: Optional[str] = None
