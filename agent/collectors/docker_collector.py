"""Collecteur d'informations Docker."""

import os
import re
import docker
from docker.errors import APIError
from datetime import datetime
from typing import Optional
import logging

import yaml

from models import (
    ContainerInfo,
    ContainerStatus,
    HealthStatus,
    PortMapping,
    VolumeMount,
    NetworkInfo,
    ContainerLogEntry,
    ContainerMetricsReport,
)

logger = logging.getLogger(__name__)


class DockerCollector:
    """Collecte les informations des conteneurs Docker."""

    def __init__(self, docker_socket: str = "unix:///var/run/docker.sock"):
        """Initialise le collecteur Docker."""
        self.client = docker.DockerClient(base_url=docker_socket)
        self._compose_cache: dict[str, dict] = {}  # Cache des fichiers compose parsés
        self._services_by_project: dict[str, list[str]] = {}  # project -> [services]

    def get_docker_version(self) -> Optional[str]:
        """Retourne la version de Docker."""
        try:
            info = self.client.version()
            return info.get("Version", "unknown")
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la version Docker: {e}")
            return None

    def collect_containers(self) -> list[ContainerInfo]:
        """Collecte les informations de tous les conteneurs."""
        containers = []

        try:
            for container in self.client.containers.list(all=True):
                container_info = self._parse_container(container)
                if container_info:
                    containers.append(container_info)
        except APIError as e:
            logger.error(f"Erreur API Docker: {e}")

        return containers

    def _parse_container(self, container) -> Optional[ContainerInfo]:
        """Parse les informations d'un conteneur."""
        try:
            # Récupérer les détails complets
            attrs = container.attrs
            config = attrs.get("Config", {})
            state = attrs.get("State", {})
            network_settings = attrs.get("NetworkSettings", {})
            host_config = attrs.get("HostConfig", {})

            # Statut
            status = self._parse_status(state.get("Status", "unknown"))

            # Santé
            health = HealthStatus.NONE
            if "Health" in state:
                health_status = state["Health"].get("Status", "none")
                health = HealthStatus(health_status) if health_status in HealthStatus.__members__.values() else HealthStatus.NONE

            # Ports
            ports = self._parse_ports(network_settings.get("Ports", {}))

            # Volumes
            volumes = self._parse_volumes(attrs.get("Mounts", []))

            # Réseaux et IPs
            networks_data = network_settings.get("Networks", {})
            networks = list(networks_data.keys())
            ip_addresses = {
                name: net.get("IPAddress", "")
                for name, net in networks_data.items()
                if net.get("IPAddress")
            }

            # Labels
            labels = config.get("Labels", {}) or {}

            # Environnement (filtrer les secrets potentiels)
            env_list = config.get("Env", []) or []
            environment = {}
            for env in env_list:
                if "=" in env:
                    key, value = env.split("=", 1)
                    # Ne pas exposer les mots de passe et secrets
                    if any(secret in key.upper() for secret in ["PASSWORD", "SECRET", "KEY", "TOKEN"]):
                        value = "***HIDDEN***"
                    environment[key] = value

            # Compose
            compose_project = labels.get("com.docker.compose.project")
            compose_service = labels.get("com.docker.compose.service")

            # Détecter les dépendances
            declared_dependencies = []
            if compose_project and compose_service:
                # 1. Depuis docker-compose.yml et .env
                compose_deps = self._get_compose_dependencies(labels, compose_project, compose_service)
                declared_dependencies.extend(compose_deps)

                # 2. Depuis les variables d'environnement
                env_deps = self._get_env_dependencies(environment, compose_project)
                for dep in env_deps:
                    if dep not in declared_dependencies and dep != compose_service:
                        declared_dependencies.append(dep)

                # 3. Depuis les logs (seulement pour les conteneurs running)
                if status == ContainerStatus.RUNNING:
                    log_deps = self._get_log_dependencies(container, compose_project)
                    for dep in log_deps:
                        if dep not in declared_dependencies and dep != compose_service:
                            declared_dependencies.append(dep)

            # Dates
            created = datetime.fromisoformat(attrs["Created"].replace("Z", "+00:00"))
            started_at = None
            if state.get("StartedAt") and state["StartedAt"] != "0001-01-01T00:00:00Z":
                started_at = datetime.fromisoformat(state["StartedAt"].replace("Z", "+00:00"))

            return ContainerInfo(
                id=container.id[:12],
                name=container.name,
                image=config.get("Image", "unknown"),
                status=status,
                health=health,
                created=created,
                started_at=started_at,
                networks=networks,
                ip_addresses=ip_addresses,
                ports=ports,
                volumes=volumes,
                labels=labels,
                environment=environment,
                compose_project=compose_project,
                compose_service=compose_service,
                declared_dependencies=declared_dependencies,
            )
        except Exception as e:
            logger.error(f"Erreur lors du parsing du conteneur {container.name}: {e}")
            return None

    def _parse_status(self, status: str) -> ContainerStatus:
        """Parse le statut d'un conteneur."""
        status_map = {
            "running": ContainerStatus.RUNNING,
            "exited": ContainerStatus.EXITED,
            "paused": ContainerStatus.PAUSED,
            "restarting": ContainerStatus.RESTARTING,
            "dead": ContainerStatus.DEAD,
            "created": ContainerStatus.CREATED,
        }
        return status_map.get(status.lower(), ContainerStatus.UNKNOWN)

    def _parse_ports(self, ports_data: dict) -> list[PortMapping]:
        """Parse les mappings de ports."""
        ports = []

        for container_port, host_bindings in ports_data.items():
            # Format: "80/tcp"
            port_parts = container_port.split("/")
            c_port = int(port_parts[0])
            protocol = port_parts[1] if len(port_parts) > 1 else "tcp"

            if host_bindings:
                for binding in host_bindings:
                    ports.append(PortMapping(
                        container_port=c_port,
                        host_port=int(binding["HostPort"]) if binding.get("HostPort") else None,
                        protocol=protocol,
                        host_ip=binding.get("HostIp", "0.0.0.0"),
                    ))
            else:
                # Port exposé mais non mappé
                ports.append(PortMapping(
                    container_port=c_port,
                    protocol=protocol,
                ))

        return ports

    def _parse_volumes(self, mounts: list) -> list[VolumeMount]:
        """Parse les montages de volumes."""
        volumes = []

        for mount in mounts:
            volumes.append(VolumeMount(
                source=mount.get("Source", ""),
                destination=mount.get("Destination", ""),
                mode=mount.get("Mode", "rw"),
                type=mount.get("Type", "bind"),
            ))

        return volumes

    def collect_networks(self) -> list[NetworkInfo]:
        """Collecte les informations des réseaux Docker."""
        networks = []

        try:
            for network in self.client.networks.list():
                attrs = network.attrs
                ipam = attrs.get("IPAM", {})
                ipam_config = ipam.get("Config", [{}])[0] if ipam.get("Config") else {}

                # Conteneurs connectés
                containers = list(attrs.get("Containers", {}).keys())
                containers = [c[:12] for c in containers]  # Short IDs

                networks.append(NetworkInfo(
                    id=network.id[:12],
                    name=network.name,
                    driver=attrs.get("Driver", "unknown"),
                    scope=attrs.get("Scope", "local"),
                    subnet=ipam_config.get("Subnet"),
                    gateway=ipam_config.get("Gateway"),
                    containers=containers,
                ))
        except APIError as e:
            logger.error(f"Erreur API Docker (réseaux): {e}")

        return networks

    def _get_compose_dependencies(self, labels: dict, compose_project: str, compose_service: str) -> list[str]:
        """
        Extrait les dépendances depuis le fichier docker-compose.yml.
        Utilise le label working_dir pour trouver le fichier.
        """
        dependencies = []

        working_dir = labels.get("com.docker.compose.project.working_dir")
        config_files = labels.get("com.docker.compose.project.config_files", "")

        if not working_dir:
            return dependencies

        # Trouver le fichier compose
        compose_files = []
        if config_files:
            compose_files = [f.strip() for f in config_files.split(",")]
        else:
            # Fichiers par défaut
            for name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
                path = os.path.join(working_dir, name)
                if os.path.exists(path):
                    compose_files.append(path)
                    break

        for compose_file in compose_files:
            if not os.path.exists(compose_file):
                # Chemin relatif au working_dir
                compose_file = os.path.join(working_dir, compose_file)
                if not os.path.exists(compose_file):
                    continue

            try:
                # Utiliser le cache si disponible
                if compose_file in self._compose_cache:
                    content = self._compose_cache[compose_file]
                else:
                    with open(compose_file, "r") as f:
                        content = yaml.safe_load(f)
                        self._compose_cache[compose_file] = content

                if not content:
                    continue

                services = content.get("services", {})

                # Stocker tous les services du projet pour la détection d'env
                if compose_project not in self._services_by_project:
                    self._services_by_project[compose_project] = list(services.keys())

                service_config = services.get(compose_service, {})

                # depends_on
                depends_on = service_config.get("depends_on", [])
                if isinstance(depends_on, list):
                    dependencies.extend(depends_on)
                elif isinstance(depends_on, dict):
                    dependencies.extend(depends_on.keys())

                # links (legacy)
                links = service_config.get("links", [])
                for link in links:
                    dep_name = link.split(":")[0]
                    if dep_name not in dependencies:
                        dependencies.append(dep_name)

                # Chercher dans .env pour les références
                env_deps = self._parse_env_file(working_dir, compose_project)
                for dep in env_deps:
                    if dep not in dependencies:
                        dependencies.append(dep)

            except yaml.YAMLError as e:
                logger.warning(f"Erreur YAML dans {compose_file}: {e}")
            except Exception as e:
                logger.debug(f"Erreur lecture compose {compose_file}: {e}")

        return dependencies

    def _parse_env_file(self, working_dir: str, compose_project: str) -> list[str]:
        """Parse le fichier .env pour trouver des références à d'autres services."""
        dependencies = []
        env_file = os.path.join(working_dir, ".env")

        if not os.path.exists(env_file):
            return dependencies

        try:
            with open(env_file, "r") as f:
                content = f.read()

            # Récupérer les services connus du projet
            known_services = self._services_by_project.get(compose_project, [])

            for service in known_services:
                # Chercher des références au service dans les URLs ou hostnames
                patterns = [
                    rf'\b{service}\b',  # Nom exact
                    rf'://{service}[:/]',  # URL
                    rf'@{service}[:/]',  # Database URL
                    rf'HOST.*=.*{service}',  # Variable HOST
                ]
                for pattern in patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        if service not in dependencies:
                            dependencies.append(service)
                        break

        except Exception as e:
            logger.debug(f"Erreur lecture .env: {e}")

        return dependencies

    def _get_env_dependencies(self, environment: dict, compose_project: str) -> list[str]:
        """Extrait les dépendances depuis les variables d'environnement."""
        dependencies = []
        known_services = self._services_by_project.get(compose_project, [])

        # Patterns courants pour les connexions
        connection_patterns = [
            r'(?:DATABASE|DB|REDIS|MONGO|POSTGRES|MYSQL|ELASTIC|RABBIT|KAFKA).*(?:HOST|URL|URI)',
            r'.*_HOST$',
            r'.*_URL$',
            r'.*_URI$',
            r'.*_SERVER$',
            r'.*_ENDPOINT$',
        ]

        for key, value in environment.items():
            if value == "***HIDDEN***":
                continue

            # Vérifier si c'est une variable de connexion
            is_connection_var = any(re.match(pattern, key, re.IGNORECASE) for pattern in connection_patterns)

            if is_connection_var and isinstance(value, str):
                # Chercher des références à d'autres services
                for service in known_services:
                    if service in value.lower():
                        if service not in dependencies:
                            dependencies.append(service)

        return dependencies

    def _get_log_dependencies(self, container, compose_project: str, max_lines: int = 100) -> list[str]:
        """Analyse les logs récents pour détecter des connexions."""
        dependencies = []
        known_services = self._services_by_project.get(compose_project, [])

        if not known_services:
            return dependencies

        try:
            logs = container.logs(tail=max_lines, timestamps=False).decode("utf-8", errors="ignore")

            # Patterns de connexion dans les logs
            connection_patterns = [
                r'[Cc]onnect(?:ed|ing)?\s+to\s+(\w+)',
                r'[Rr]esolv(?:ed|ing)?\s+(\w+)',
                r'http[s]?://(\w+)[:/]',
                r'@(\w+):',  # Database URLs
            ]

            for pattern in connection_patterns:
                matches = re.findall(pattern, logs)
                for match in matches:
                    match_lower = match.lower()
                    for service in known_services:
                        if service.lower() == match_lower:
                            if service not in dependencies:
                                dependencies.append(service)

        except Exception as e:
            logger.debug(f"Erreur lecture logs: {e}")

        return dependencies

    def get_container_logs(
        self,
        container_id: str,
        lines: int = 100,
        since_seconds: int = 60
    ) -> list[ContainerLogEntry]:
        """
        Récupère les derniers logs d'un container.

        Args:
            container_id: ID du container (short ou long)
            lines: Nombre de lignes max
            since_seconds: Récupérer les logs depuis N secondes

        Returns:
            Liste des entrées de log
        """
        entries = []
        try:
            container = self.client.containers.get(container_id)

            # Calculer le timestamp "since"
            since_timestamp = int(datetime.utcnow().timestamp()) - since_seconds

            # Récupérer les logs avec timestamps
            logs_stdout = container.logs(
                stdout=True,
                stderr=False,
                tail=lines,
                since=since_timestamp,
                timestamps=True,
                stream=False
            )
            logs_stderr = container.logs(
                stdout=False,
                stderr=True,
                tail=lines,
                since=since_timestamp,
                timestamps=True,
                stream=False
            )

            # Parser les logs stdout
            for line in logs_stdout.decode("utf-8", errors="ignore").split("\n"):
                if not line.strip():
                    continue
                entry = self._parse_log_line(container_id, line, "stdout")
                if entry:
                    entries.append(entry)

            # Parser les logs stderr
            for line in logs_stderr.decode("utf-8", errors="ignore").split("\n"):
                if not line.strip():
                    continue
                entry = self._parse_log_line(container_id, line, "stderr")
                if entry:
                    entries.append(entry)

        except docker.errors.NotFound:
            logger.debug(f"Container {container_id} not found for logs")
        except Exception as e:
            logger.debug(f"Erreur récupération logs {container_id}: {e}")

        return entries

    def _parse_log_line(
        self,
        container_id: str,
        line: str,
        stream: str
    ) -> Optional[ContainerLogEntry]:
        """Parse une ligne de log Docker avec timestamp."""
        try:
            # Format Docker: "2024-01-15T10:30:45.123456789Z message"
            # Le timestamp est séparé du message par un espace
            parts = line.split(" ", 1)
            if len(parts) >= 2:
                timestamp = parts[0]
                message = parts[1]
            else:
                # Pas de timestamp, utiliser maintenant
                timestamp = datetime.utcnow().isoformat() + "Z"
                message = line

            # Tronquer le message si trop long
            if len(message) > 5000:
                message = message[:5000] + "..."

            return ContainerLogEntry(
                container_id=container_id,
                timestamp=timestamp,
                stream=stream,
                message=message
            )
        except Exception as e:
            logger.debug(f"Erreur parse log line: {e}")
            return None

    def collect_all_container_logs(
        self,
        containers: list[ContainerInfo],
        lines: int = 100,
        since_seconds: int = 60
    ) -> list[ContainerLogEntry]:
        """
        Collecte les logs de tous les containers running.

        Args:
            containers: Liste des containers
            lines: Nombre de lignes par container
            since_seconds: Logs depuis N secondes

        Returns:
            Liste de toutes les entrées de log
        """
        all_logs = []

        for container in containers:
            # Ne collecter que les containers running
            if container.status != ContainerStatus.RUNNING:
                continue

            logs = self.get_container_logs(
                container.id,
                lines=lines,
                since_seconds=since_seconds
            )
            all_logs.extend(logs)

        logger.debug(f"Collecté {len(all_logs)} lignes de logs de {len(containers)} containers")
        return all_logs

    def close(self):
        """Ferme la connexion Docker."""
        self.client.close()

    # === Container Control Actions ===

    def start_container(self, container_id: str) -> dict:
        """Démarre un container."""
        try:
            container = self.client.containers.get(container_id)
            container.start()
            return {"success": True, "message": f"Container {container_id} started"}
        except docker.errors.NotFound:
            return {"success": False, "error": f"Container {container_id} not found"}
        except APIError as e:
            return {"success": False, "error": str(e)}

    def stop_container(self, container_id: str, timeout: int = 10) -> dict:
        """Arrête un container."""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=timeout)
            return {"success": True, "message": f"Container {container_id} stopped"}
        except docker.errors.NotFound:
            return {"success": False, "error": f"Container {container_id} not found"}
        except APIError as e:
            return {"success": False, "error": str(e)}

    def restart_container(self, container_id: str, timeout: int = 10) -> dict:
        """Redémarre un container."""
        try:
            container = self.client.containers.get(container_id)
            container.restart(timeout=timeout)
            return {"success": True, "message": f"Container {container_id} restarted"}
        except docker.errors.NotFound:
            return {"success": False, "error": f"Container {container_id} not found"}
        except APIError as e:
            return {"success": False, "error": str(e)}

    def exec_container(
        self,
        container_id: str,
        command: str,
        timeout: int = 30,
        workdir: str = None
    ) -> dict:
        """
        Exécute une commande dans un container.

        Args:
            container_id: ID du container
            command: Commande à exécuter
            timeout: Timeout en secondes
            workdir: Répertoire de travail (optionnel)

        Returns:
            Dict avec exit_code, stdout, stderr
        """
        try:
            container = self.client.containers.get(container_id)

            # Vérifier que le container est running
            if container.status != "running":
                return {
                    "success": False,
                    "error": f"Container {container_id} is not running (status: {container.status})"
                }

            # Exécuter la commande
            exec_result = container.exec_run(
                cmd=command,
                stdout=True,
                stderr=True,
                workdir=workdir,
                demux=True  # Sépare stdout et stderr
            )

            stdout = exec_result.output[0].decode("utf-8", errors="replace") if exec_result.output[0] else ""
            stderr = exec_result.output[1].decode("utf-8", errors="replace") if exec_result.output[1] else ""

            # Limiter la taille de la sortie
            max_output = 50000
            if len(stdout) > max_output:
                stdout = stdout[:max_output] + "\n... (output truncated)"
            if len(stderr) > max_output:
                stderr = stderr[:max_output] + "\n... (output truncated)"

            return {
                "success": True,
                "exit_code": exec_result.exit_code,
                "stdout": stdout,
                "stderr": stderr
            }

        except docker.errors.NotFound:
            return {"success": False, "error": f"Container {container_id} not found"}
        except APIError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_container_stats(self, container_id: str) -> dict:
        """Récupère les statistiques d'un container."""
        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)

            # Calculer CPU %
            cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                        stats["precpu_stats"]["cpu_usage"]["total_usage"]
            system_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                           stats["precpu_stats"]["system_cpu_usage"]
            cpu_count = stats["cpu_stats"].get("online_cpus", 1)
            cpu_percent = (cpu_delta / system_delta) * cpu_count * 100 if system_delta > 0 else 0

            # Mémoire
            memory_usage = stats["memory_stats"].get("usage", 0)
            memory_limit = stats["memory_stats"].get("limit", 1)
            memory_percent = (memory_usage / memory_limit) * 100

            return {
                "success": True,
                "stats": {
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_usage_mb": round(memory_usage / (1024 * 1024), 2),
                    "memory_limit_mb": round(memory_limit / (1024 * 1024), 2),
                    "memory_percent": round(memory_percent, 2),
                    "network_rx_bytes": sum(
                        net.get("rx_bytes", 0)
                        for net in stats.get("networks", {}).values()
                    ),
                    "network_tx_bytes": sum(
                        net.get("tx_bytes", 0)
                        for net in stats.get("networks", {}).values()
                    ),
                }
            }
        except docker.errors.NotFound:
            return {"success": False, "error": f"Container {container_id} not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def collect_container_metrics(self, containers: list[ContainerInfo]) -> list[ContainerMetricsReport]:
        """Collecte les métriques de tous les containers running."""
        metrics = []

        for container_info in containers:
            # Ne collecter que les containers running
            if container_info.status != ContainerStatus.RUNNING:
                continue

            try:
                container = self.client.containers.get(container_info.id)
                stats = container.stats(stream=False)

                # Calculer CPU %
                cpu_percent = 0.0
                try:
                    cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                                stats["precpu_stats"]["cpu_usage"]["total_usage"]
                    system_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                                   stats["precpu_stats"]["system_cpu_usage"]
                    cpu_count = stats["cpu_stats"].get("online_cpus", 1)
                    if system_delta > 0:
                        cpu_percent = (cpu_delta / system_delta) * cpu_count * 100
                except (KeyError, TypeError, ZeroDivisionError):
                    pass

                # Mémoire
                memory_used = 0
                memory_limit = 0
                memory_percent = 0.0
                try:
                    memory_used = stats["memory_stats"].get("usage", 0)
                    memory_limit = stats["memory_stats"].get("limit", 1)
                    if memory_limit > 0:
                        memory_percent = (memory_used / memory_limit) * 100
                except (KeyError, TypeError, ZeroDivisionError):
                    pass

                # Réseau
                network_rx = 0
                network_tx = 0
                try:
                    for net in stats.get("networks", {}).values():
                        network_rx += net.get("rx_bytes", 0)
                        network_tx += net.get("tx_bytes", 0)
                except (KeyError, TypeError):
                    pass

                # Block I/O
                disk_read = 0
                disk_write = 0
                try:
                    for io_entry in stats.get("blkio_stats", {}).get("io_service_bytes_recursive", []) or []:
                        if io_entry.get("op") == "read":
                            disk_read += io_entry.get("value", 0)
                        elif io_entry.get("op") == "write":
                            disk_write += io_entry.get("value", 0)
                except (KeyError, TypeError):
                    pass

                # PIDs
                pids = 0
                try:
                    pids = stats.get("pids_stats", {}).get("current", 0)
                except (KeyError, TypeError):
                    pass

                metrics.append(ContainerMetricsReport(
                    container_id=container_info.id,
                    cpu_percent=round(cpu_percent, 2),
                    memory_used=int(memory_used / (1024 * 1024)),  # MB
                    memory_limit=int(memory_limit / (1024 * 1024)),  # MB
                    memory_percent=round(memory_percent, 2),
                    network_rx_bytes=network_rx,
                    network_tx_bytes=network_tx,
                    disk_read_bytes=disk_read,
                    disk_write_bytes=disk_write,
                    pids=pids,
                ))

            except docker.errors.NotFound:
                logger.debug(f"Container {container_info.id} not found for metrics")
            except Exception as e:
                logger.debug(f"Erreur métriques container {container_info.name}: {e}")

        return metrics
