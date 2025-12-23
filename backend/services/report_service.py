"""Service de traitement des rapports d'agents."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Host, Container, Network, Connection, ContainerLog, Vm, ContainerStatusEnum, HealthStatusEnum, VmStatusEnum
from models.schemas import AgentReport
from services.logs_service import LogsService
from services.metrics_service import MetricsService

logger = logging.getLogger(__name__)


def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convertit un datetime timezone-aware en naive UTC."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Convertir en UTC puis supprimer le tzinfo
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class ReportService:
    """Service de traitement des rapports d'agents."""

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db

    async def process_report(self, report: AgentReport) -> dict:
        """
        Traite un rapport d'agent et met à jour la base de données.

        Retourne un résumé des modifications.
        """
        host_id = report.host.agent_id
        stats = {
            "host_updated": False,
            "containers_added": 0,
            "containers_updated": 0,
            "containers_removed": 0,
            "networks_updated": 0,
            "connections_updated": 0,
            "logs_stored": 0,
            "metrics_stored": 0,
        }

        # 1. Mettre à jour l'hôte
        await self._update_host(report)
        stats["host_updated"] = True

        # 2. Mettre à jour les conteneurs
        container_stats = await self._update_containers(host_id, report.containers)
        stats.update(container_stats)

        # 3. Mettre à jour les réseaux
        await self._update_networks(host_id, report.networks)
        stats["networks_updated"] = len(report.networks)

        # 4. Mettre à jour les connexions
        await self._update_connections(host_id, report.connections, report.containers)
        stats["connections_updated"] = len(report.connections)

        # 5. Stocker les logs des containers
        if report.container_logs:
            logs_service = LogsService(self.db)
            logs_data = [
                {
                    "container_id": log.container_id,
                    "timestamp": log.timestamp,
                    "message": log.message,
                    "stream": log.stream,
                }
                for log in report.container_logs
            ]
            stats["logs_stored"] = await logs_service.store_logs(host_id, logs_data)

        # 6. Stocker les métriques
        metrics_count = await self._store_metrics(host_id, report)
        stats["metrics_stored"] = metrics_count

        await self.db.commit()

        logger.info(f"Rapport traité pour {host_id}: {stats}")
        return stats

    async def _update_host(self, report: AgentReport):
        """Met à jour ou crée l'hôte."""
        host_info = report.host

        # Chercher l'hôte existant
        result = await self.db.execute(
            select(Host).where(Host.id == host_info.agent_id)
        )
        host = result.scalar_one_or_none()

        tailscale_ip = None
        tailscale_hostname = None
        if host_info.tailscale and host_info.tailscale.enabled:
            tailscale_ip = host_info.tailscale.ip
            tailscale_hostname = host_info.tailscale.hostname

        if host:
            # Mettre à jour
            host.hostname = host_info.hostname
            host.ip_addresses = host_info.ip_addresses
            host.tailscale_ip = tailscale_ip
            host.tailscale_hostname = tailscale_hostname
            host.docker_version = host_info.docker_version
            host.last_seen = datetime.utcnow()
            host.is_online = True
        else:
            # Créer
            host = Host(
                id=host_info.agent_id,
                hostname=host_info.hostname,
                ip_addresses=host_info.ip_addresses,
                tailscale_ip=tailscale_ip,
                tailscale_hostname=tailscale_hostname,
                docker_version=host_info.docker_version,
                is_online=True,
            )
            self.db.add(host)

        # Auto-découverte: créer/mettre à jour la VM correspondante
        await self._auto_discover_vm(host_info, host)

    async def _auto_discover_vm(self, host_info, host: Host):
        """Crée ou met à jour une VM auto-découverte depuis un agent."""
        import uuid
        from sqlalchemy import or_

        # Chercher une VM existante liée à ce host
        result = await self.db.execute(
            select(Vm).where(Vm.host_id == host.id)
        )
        vm = result.scalar_one_or_none()

        # Déterminer l'IP à utiliser
        ip_address = host.tailscale_ip
        if not ip_address and host.ip_addresses:
            # Prendre la première IP non-localhost
            for ip in host.ip_addresses:
                if not ip.startswith("127.") and not ip.startswith("::1"):
                    ip_address = ip
                    break
        if not ip_address:
            ip_address = "unknown"

        # Si pas trouvé par host_id, chercher par IP (VM créée manuellement)
        # Essayer avec l'IP Tailscale d'abord, puis l'IP principale
        if not vm:
            ips_to_check = []
            if host.tailscale_ip:
                ips_to_check.append(host.tailscale_ip)
            if ip_address and ip_address != "unknown":
                ips_to_check.append(ip_address)
            # Ajouter aussi toutes les IPs de l'hôte
            if host.ip_addresses:
                ips_to_check.extend(host.ip_addresses)

            for ip in ips_to_check:
                result = await self.db.execute(
                    select(Vm).where(
                        Vm.host_id.is_(None),
                        Vm.ip_address == ip
                    )
                )
                vm = result.scalar_one_or_none()
                if vm:
                    # Lier la VM existante à ce host
                    vm.host_id = host.id
                    logger.info(f"VM {vm.name} liée à l'agent {host.id} (via IP {ip})")
                    break

        if vm:
            # Mettre à jour le statut
            vm.status = VmStatusEnum.ONLINE
            vm.hostname = host_info.hostname
            # Ne mettre à jour l'IP que si la VM est auto-découverte
            # (préserver l'IP Tailscale/Headscale configurée manuellement)
            if vm.is_auto_discovered and ip_address != "unknown":
                vm.ip_address = ip_address
        else:
            # Créer une nouvelle VM auto-découverte
            vm = Vm(
                id=str(uuid.uuid4()),
                name=host_info.hostname,
                hostname=host_info.hostname,
                ip_address=ip_address,
                host_id=host.id,
                status=VmStatusEnum.ONLINE,
                is_auto_discovered=True,
            )
            self.db.add(vm)
            logger.info(f"VM auto-découverte créée: {host_info.hostname}")

    async def _update_containers(self, host_id: str, containers: list) -> dict:
        """Met à jour les conteneurs d'un hôte."""
        stats = {"containers_added": 0, "containers_updated": 0, "containers_removed": 0}

        # Récupérer les conteneurs existants
        result = await self.db.execute(
            select(Container).where(Container.host_id == host_id)
        )
        existing = {c.container_id: c for c in result.scalars().all()}

        # IDs des conteneurs dans le rapport
        reported_ids = {c.id for c in containers}

        # Supprimer les conteneurs qui n'existent plus
        for container_id, container in existing.items():
            if container_id not in reported_ids:
                await self.db.delete(container)
                stats["containers_removed"] += 1

        # Ajouter/mettre à jour les conteneurs
        for container_info in containers:
            full_id = f"{host_id}:{container_info.id}"

            if container_info.id in existing:
                # Mettre à jour
                container = existing[container_info.id]
                self._update_container_fields(container, container_info)
                stats["containers_updated"] += 1
            else:
                # Créer
                container = Container(
                    id=full_id,
                    container_id=container_info.id,
                    host_id=host_id,
                )
                self._update_container_fields(container, container_info)
                self.db.add(container)
                stats["containers_added"] += 1

        return stats

    def _update_container_fields(self, container: Container, info):
        """Met à jour les champs d'un conteneur."""
        container.name = info.name
        container.image = info.image
        container.status = ContainerStatusEnum(info.status.value)
        container.health = HealthStatusEnum(info.health.value)
        container.networks = info.networks
        container.ip_addresses = info.ip_addresses
        container.ports = [p.model_dump() for p in info.ports]
        container.volumes = [v.model_dump() for v in info.volumes]
        container.labels = info.labels
        container.environment = info.environment
        container.compose_project = info.compose_project
        container.compose_service = info.compose_service
        container.declared_dependencies = info.declared_dependencies
        container.created_at = to_naive_utc(info.created)
        container.started_at = to_naive_utc(info.started_at)
        container.last_seen = datetime.utcnow()

    async def _update_networks(self, host_id: str, networks: list):
        """Met à jour les réseaux d'un hôte."""
        # Supprimer les anciens réseaux
        await self.db.execute(
            delete(Network).where(Network.host_id == host_id)
        )

        # Ajouter les nouveaux
        for network_info in networks:
            network = Network(
                id=f"{host_id}:{network_info.id}",
                network_id=network_info.id,
                host_id=host_id,
                name=network_info.name,
                driver=network_info.driver,
                scope=network_info.scope,
                subnet=network_info.subnet,
                gateway=network_info.gateway,
                containers=network_info.containers,
            )
            self.db.add(network)

    async def _update_connections(self, host_id: str, connections: list, containers: list):
        """Met à jour les connexions réseau."""
        # Créer un mapping IP -> container_id pour ce host
        ip_to_container = {}
        for container in containers:
            for network, ip in container.ip_addresses.items():
                if ip:
                    ip_to_container[ip] = container.id

        # Supprimer les anciennes connexions de cet hôte
        await self.db.execute(
            delete(Connection).where(Connection.source_host_id == host_id)
        )

        # Filtrer les connexions intéressantes (pas localhost, pas les écoutes)
        for conn in connections:
            # Ignorer les connexions LISTEN et localhost
            if conn.state == "LISTEN":
                continue
            if conn.remote_ip in ("127.0.0.1", "::1", "0.0.0.0"):
                continue

            # Déterminer le type de connexion
            connection_type = self._determine_connection_type(conn, ip_to_container)

            # Utiliser le container_id envoyé par l'agent, sinon fallback sur IP
            source_container_id = conn.container_id or ip_to_container.get(conn.local_ip)

            connection = Connection(
                source_host_id=host_id,
                source_container_id=source_container_id,
                source_ip=conn.local_ip,
                source_port=conn.local_port,
                target_ip=conn.remote_ip,
                target_port=conn.remote_port,
                protocol=conn.protocol,
                state=conn.state,
                connection_type=connection_type,
                source_method=getattr(conn, 'source_method', 'proc_net'),
            )
            self.db.add(connection)

    def _determine_connection_type(self, conn, ip_to_container: dict) -> str:
        """Détermine le type de connexion."""
        # Si l'IP distante est dans nos conteneurs, c'est interne
        if conn.remote_ip in ip_to_container:
            return "internal"

        # Si c'est une IP privée, probablement cross-host
        if self._is_private_ip(conn.remote_ip):
            return "cross-host"

        # Sinon, c'est externe
        return "external"

    def _is_private_ip(self, ip: str) -> bool:
        """Vérifie si une IP est privée."""
        if ip.startswith("10."):
            return True
        if ip.startswith("172."):
            # 172.16.0.0 - 172.31.255.255
            parts = ip.split(".")
            if len(parts) >= 2 and 16 <= int(parts[1]) <= 31:
                return True
        if ip.startswith("192.168."):
            return True
        if ip.startswith("100.64."):  # Tailscale CGNAT
            return True
        return False

    async def _store_metrics(self, host_id: str, report: AgentReport) -> int:
        """Stocke les métriques du rapport."""
        metrics_service = MetricsService(self.db)
        count = 0

        # Métriques host
        if report.host_metrics:
            metrics_dict = {
                "cpu_percent": report.host_metrics.cpu_percent,
                "cpu_count": report.host_metrics.cpu_count,
                "load_1m": report.host_metrics.load_1m,
                "load_5m": report.host_metrics.load_5m,
                "load_15m": report.host_metrics.load_15m,
                "memory_total": report.host_metrics.memory_total,
                "memory_used": report.host_metrics.memory_used,
                "memory_percent": report.host_metrics.memory_percent,
                "disk_total": report.host_metrics.disk_total,
                "disk_used": report.host_metrics.disk_used,
                "disk_percent": report.host_metrics.disk_percent,
                "network_rx_bytes": report.host_metrics.network_rx_bytes,
                "network_tx_bytes": report.host_metrics.network_tx_bytes,
            }
            await metrics_service.store_host_metrics(host_id, metrics_dict)
            count += 1

        # Métriques containers
        if report.container_metrics:
            containers_data = [
                {
                    "container_id": cm.container_id,
                    "metrics": {
                        "cpu_percent": cm.cpu_percent,
                        "memory_used": cm.memory_used,
                        "memory_limit": cm.memory_limit,
                        "memory_percent": cm.memory_percent,
                        "network_rx_bytes": cm.network_rx_bytes,
                        "network_tx_bytes": cm.network_tx_bytes,
                        "disk_read_bytes": cm.disk_read_bytes,
                        "disk_write_bytes": cm.disk_write_bytes,
                        "pids": cm.pids,
                    }
                }
                for cm in report.container_metrics
            ]
            count += await metrics_service.store_bulk_container_metrics(host_id, containers_data)

        return count
