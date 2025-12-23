"""Configuration de l'agent Infra-Mapper."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class AgentConfig(BaseSettings):
    """Configuration de l'agent."""

    # Backend
    backend_url: str = Field(
        default="http://localhost:8000",
        description="URL du backend Infra-Mapper"
    )
    api_key: str = Field(
        default="change-me-in-production",
        description="Clé API pour l'authentification"
    )

    # Agent
    agent_id: Optional[str] = Field(
        default=None,
        description="ID unique de l'agent (auto-généré si non spécifié)"
    )
    hostname: Optional[str] = Field(
        default=None,
        description="Nom de l'hôte (auto-détecté si non spécifié)"
    )
    scan_interval: int = Field(
        default=30,
        description="Intervalle entre les scans (en secondes)"
    )

    # Docker
    docker_socket: str = Field(
        default="unix:///var/run/docker.sock",
        description="Chemin vers le socket Docker"
    )
    compose_search_paths: list[str] = Field(
        default=["/root", "/home", "/opt", "/srv"],
        description="Chemins où chercher les docker-compose.yml"
    )

    # Tailscale
    tailscale_enabled: bool = Field(
        default=True,
        description="Activer la détection Tailscale"
    )

    # Tcpdump
    tcpdump_enabled: bool = Field(
        default=True,
        description="Activer la capture tcpdump"
    )
    tcpdump_mode: str = Field(
        default="intermittent",
        description="Mode tcpdump: 'intermittent' (30s toutes les 10min) ou 'active' (continu)"
    )
    tcpdump_duration: int = Field(
        default=30,
        description="Durée de capture tcpdump en secondes"
    )
    tcpdump_interval: int = Field(
        default=600,
        description="Intervalle entre captures tcpdump en secondes (mode intermittent)"
    )
    tcpdump_max_packets: int = Field(
        default=500,
        description="Nombre max de paquets par conteneur"
    )

    # Container logs collection
    collect_logs: bool = Field(
        default=True,
        description="Collecter les logs des containers"
    )
    logs_lines: int = Field(
        default=100,
        description="Nombre de lignes de logs à collecter par container"
    )
    logs_since_seconds: int = Field(
        default=60,
        description="Collecter les logs depuis les N dernières secondes"
    )

    # Command server (for remote control)
    command_server_enabled: bool = Field(
        default=True,
        description="Activer le serveur de commandes pour le contrôle distant"
    )
    command_server_port: int = Field(
        default=8081,
        description="Port du serveur de commandes"
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Niveau de log"
    )

    class Config:
        env_prefix = "MAPPER_"
        env_file = ".env"


def get_config() -> AgentConfig:
    """Retourne la configuration de l'agent."""
    return AgentConfig()
