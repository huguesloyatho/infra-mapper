"""Modèles de données pour l'agent Infra-Mapper."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class ContainerStatus(str, Enum):
    """Statut d'un conteneur."""
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESTARTING = "restarting"
    EXITED = "exited"
    DEAD = "dead"
    CREATED = "created"
    UNKNOWN = "unknown"


class HealthStatus(str, Enum):
    """Statut de santé d'un conteneur."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    NONE = "none"


class PortMapping(BaseModel):
    """Mapping de port."""
    container_port: int
    host_port: Optional[int] = None
    protocol: str = "tcp"
    host_ip: str = "0.0.0.0"


class VolumeMount(BaseModel):
    """Point de montage de volume."""
    source: str
    destination: str
    mode: str = "rw"
    type: str = "bind"


class NetworkConnection(BaseModel):
    """Connexion réseau active."""
    protocol: str  # tcp, udp
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    state: str  # ESTABLISHED, LISTEN, etc.
    pid: Optional[int] = None
    process_name: Optional[str] = None
    container_id: Optional[str] = None
    source_method: str = "proc_net"  # proc_net, tcpdump


class ContainerInfo(BaseModel):
    """Informations sur un conteneur."""
    id: str
    name: str
    image: str
    status: ContainerStatus
    health: HealthStatus = HealthStatus.NONE
    created: datetime
    started_at: Optional[datetime] = None

    # Réseau
    networks: list[str] = Field(default_factory=list)
    ip_addresses: dict[str, str] = Field(default_factory=dict)  # network -> ip
    ports: list[PortMapping] = Field(default_factory=list)

    # Volumes
    volumes: list[VolumeMount] = Field(default_factory=list)

    # Labels et environnement
    labels: dict[str, str] = Field(default_factory=dict)
    environment: dict[str, str] = Field(default_factory=dict)

    # Compose
    compose_project: Optional[str] = None
    compose_service: Optional[str] = None

    # Dépendances déclarées (depuis docker-compose)
    declared_dependencies: list[str] = Field(default_factory=list)


class NetworkInfo(BaseModel):
    """Informations sur un réseau Docker."""
    id: str
    name: str
    driver: str
    scope: str
    subnet: Optional[str] = None
    gateway: Optional[str] = None
    containers: list[str] = Field(default_factory=list)  # Liste des IDs


class TailscaleInfo(BaseModel):
    """Informations Tailscale de l'hôte."""
    enabled: bool = False
    ip: Optional[str] = None
    hostname: Optional[str] = None
    tailnet: Optional[str] = None
    peers: dict[str, str] = Field(default_factory=dict)  # hostname -> ip


class HostInfo(BaseModel):
    """Informations sur l'hôte."""
    agent_id: str
    hostname: str
    ip_addresses: list[str] = Field(default_factory=list)
    tailscale: Optional[TailscaleInfo] = None
    os_info: Optional[str] = None
    docker_version: Optional[str] = None


class ContainerLogEntry(BaseModel):
    """Entrée de log d'un container."""
    container_id: str
    timestamp: str  # ISO format
    stream: str = "stdout"  # stdout, stderr
    message: str


class AgentMetadata(BaseModel):
    """Métadonnées de l'agent pour le monitoring."""
    version: Optional[str] = None  # Version de l'agent (ex: "1.2.3")
    report_interval: Optional[int] = None  # Intervalle de rapport configuré en secondes
    report_duration_ms: Optional[int] = None  # Durée de génération du rapport en ms
    uptime_seconds: Optional[int] = None  # Uptime de l'agent depuis démarrage
    error: Optional[str] = None  # Message d'erreur si le rapport contient une erreur
    command_port: Optional[int] = None  # Port du serveur de commandes (si actif)


class HostMetricsReport(BaseModel):
    """Métriques système du host."""
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
    """Métriques d'un container."""
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
    """Rapport complet envoyé par un agent."""
    host: HostInfo
    containers: list[ContainerInfo] = Field(default_factory=list)
    networks: list[NetworkInfo] = Field(default_factory=list)
    connections: list[NetworkConnection] = Field(default_factory=list)
    container_logs: list[ContainerLogEntry] = Field(default_factory=list)
    host_metrics: Optional[HostMetricsReport] = None
    container_metrics: list[ContainerMetricsReport] = Field(default_factory=list)
    agent: Optional[AgentMetadata] = None  # Métadonnées de l'agent pour le monitoring
    timestamp: datetime = Field(default_factory=datetime.utcnow)
