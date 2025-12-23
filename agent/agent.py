"""Agent principal Infra-Mapper."""

import os
import socket
import logging
import time
import uuid
from datetime import datetime

import httpx
import schedule

from config import get_config, AgentConfig
from models import AgentReport, HostInfo, AgentMetadata, HostMetricsReport, ContainerMetricsReport
from collectors import (
    DockerCollector,
    NetworkCollector,
    TailscaleCollector,
    TcpdumpCollector,
    TcpdumpMode,
    MetricsCollector,
)
from command_server import CommandServer

# Version de l'agent
AGENT_VERSION = "1.2.0"

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("infra-mapper-agent")


class InfraMapperAgent:
    """Agent de collecte Infra-Mapper."""

    def __init__(self, config: AgentConfig = None):
        """Initialise l'agent."""
        self.config = config or get_config()

        # Configuration du logging
        logging.getLogger().setLevel(getattr(logging, self.config.log_level.upper()))

        # ID de l'agent
        self.agent_id = self.config.agent_id or self._generate_agent_id()

        # Hostname
        self.hostname = self.config.hostname or socket.gethostname()

        # Temps de démarrage pour calculer l'uptime
        self.start_time = time.time()

        # Dernière erreur rencontrée
        self.last_error: str = None

        # Serveur de commandes
        self.command_server: CommandServer = None

        # Collecteurs
        self.docker_collector = DockerCollector(self.config.docker_socket)
        self.network_collector = NetworkCollector()
        self.tailscale_collector = TailscaleCollector()
        self.metrics_collector = MetricsCollector()
        # Tcpdump collector avec mode configurable
        if self.config.tcpdump_enabled:
            tcpdump_mode = TcpdumpMode(self.config.tcpdump_mode)
            self.tcpdump_collector = TcpdumpCollector(
                mode=tcpdump_mode,
                capture_duration=self.config.tcpdump_duration,
                capture_interval=self.config.tcpdump_interval,
                max_packets_per_container=self.config.tcpdump_max_packets,
            )
            logger.info(
                f"Tcpdump activé: mode={tcpdump_mode.value}, "
                f"durée={self.config.tcpdump_duration}s, "
                f"intervalle={self.config.tcpdump_interval}s"
            )
        else:
            self.tcpdump_collector = None

        # Client HTTP
        self.http_client = httpx.Client(
            base_url=self.config.backend_url,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

        logger.info(f"Agent initialisé: {self.agent_id} ({self.hostname})")

    def _generate_agent_id(self) -> str:
        """Génère un ID stable et unique pour l'agent basé sur la machine."""
        hostname = socket.gethostname()

        # Essayer de lire le machine-id Linux (stable entre redémarrages)
        machine_id = None
        for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                with open(path, "r") as f:
                    machine_id = f.read().strip()[:8]
                    break
            except (FileNotFoundError, PermissionError):
                continue

        if machine_id:
            return f"{hostname}-{machine_id}"

        # Fallback: utiliser un hash du hostname (moins unique mais stable)
        import hashlib
        hostname_hash = hashlib.md5(hostname.encode()).hexdigest()[:8]
        return f"{hostname}-{hostname_hash}"

    def collect(self) -> AgentReport:
        """Collecte toutes les informations."""
        logger.info("Début de la collecte...")
        collect_start = time.time()

        # Collecter les informations de l'hôte
        local_ips = self.network_collector.get_local_ips()
        tailscale_info = None
        if self.config.tailscale_enabled:
            tailscale_info = self.tailscale_collector.collect()

        host_info = HostInfo(
            agent_id=self.agent_id,
            hostname=self.hostname,
            ip_addresses=local_ips,
            tailscale=tailscale_info,
            docker_version=self.docker_collector.get_docker_version(),
        )

        # Collecter les conteneurs (les dépendances sont maintenant détectées dans DockerCollector)
        containers = self.docker_collector.collect_containers()

        # Collecter les réseaux
        networks = self.docker_collector.collect_networks()

        # Collecter les connexions réseau (proc_net)
        connections = self.network_collector.collect_connections()

        # Collecter les connexions via tcpdump (capture par namespace conteneur)
        tcpdump_connections = []
        if self.tcpdump_collector:
            # Le nouveau collector capture directement dans les namespaces réseau
            # et associe automatiquement le container_id
            tcpdump_connections = self.tcpdump_collector.collect(containers)

        # Fusionner et dédupliquer les connexions
        all_connections = self._merge_connections(connections, tcpdump_connections)

        # Collecter les logs des containers
        container_logs = []
        if self.config.collect_logs:
            container_logs = self.docker_collector.collect_all_container_logs(
                containers,
                lines=self.config.logs_lines,
                since_seconds=self.config.logs_since_seconds
            )

        # Collecter les métriques host
        host_metrics = self.metrics_collector.collect_host_metrics()

        # Collecter les métriques containers
        container_metrics = self.docker_collector.collect_container_metrics(containers)

        # Calculer la durée de collecte et l'uptime
        collect_duration_ms = int((time.time() - collect_start) * 1000)
        uptime_seconds = int(time.time() - self.start_time)

        # Métadonnées de l'agent
        agent_metadata = AgentMetadata(
            version=AGENT_VERSION,
            report_interval=self.config.scan_interval,
            report_duration_ms=collect_duration_ms,
            uptime_seconds=uptime_seconds,
            error=self.last_error,
            command_port=self.config.command_server_port if self.config.command_server_enabled else None,
        )

        # Reset de la dernière erreur après l'avoir envoyée
        self.last_error = None

        report = AgentReport(
            host=host_info,
            containers=containers,
            networks=networks,
            connections=all_connections,
            container_logs=container_logs,
            host_metrics=host_metrics,
            container_metrics=container_metrics,
            agent=agent_metadata,
            timestamp=datetime.utcnow(),
        )

        logger.info(
            f"Collecte terminée en {collect_duration_ms}ms: {len(containers)} conteneurs, "
            f"{len(networks)} réseaux, {len(all_connections)} connexions "
            f"({len(connections)} proc_net, {len(tcpdump_connections)} tcpdump), "
            f"{len(container_logs)} logs, {len(container_metrics)} métriques containers"
        )

        return report

    def _merge_connections(self, proc_net_conns: list, tcpdump_conns: list) -> list:
        """
        Fusionne les connexions de proc_net et tcpdump.
        Priorise proc_net car il a le container_id.
        """
        # Clé de déduplication: (local_ip, local_port, remote_ip, remote_port, protocol)
        seen = {}

        # D'abord ajouter les connexions proc_net (ont le container_id)
        for conn in proc_net_conns:
            key = (conn.local_ip, conn.local_port, conn.remote_ip, conn.remote_port, conn.protocol)
            seen[key] = conn

        # Ajouter les connexions tcpdump uniquement si pas déjà vues
        added_from_tcpdump = 0
        for conn in tcpdump_conns:
            key = (conn.local_ip, conn.local_port, conn.remote_ip, conn.remote_port, conn.protocol)
            if key not in seen:
                seen[key] = conn
                added_from_tcpdump += 1

        if added_from_tcpdump > 0:
            logger.debug(f"tcpdump: {added_from_tcpdump} nouvelles connexions ajoutées")

        return list(seen.values())

    def send_report(self, report: AgentReport) -> bool:
        """Envoie le rapport au backend."""
        try:
            response = self.http_client.post(
                "/api/v1/report",
                json=report.model_dump(mode="json"),
            )

            if response.status_code == 200:
                logger.info("Rapport envoyé avec succès")
                return True
            else:
                logger.error(f"Erreur envoi rapport: {response.status_code} - {response.text}")
                return False

        except httpx.RequestError as e:
            logger.error(f"Erreur de connexion au backend: {e}")
            return False

    def run_once(self):
        """Exécute une collecte et envoi."""
        try:
            report = self.collect()
            success = self.send_report(report)
            if not success:
                self.last_error = "Échec envoi rapport au backend"
        except Exception as e:
            logger.error(f"Erreur lors de la collecte: {e}", exc_info=True)
            self.last_error = str(e)

    def run(self):
        """Démarre l'agent en mode continu."""
        logger.info(f"Démarrage de l'agent (intervalle: {self.config.scan_interval}s)")

        # Démarrer le serveur de commandes
        if self.config.command_server_enabled:
            self.command_server = CommandServer(
                docker_collector=self.docker_collector,
                api_key=self.config.api_key,
                port=self.config.command_server_port,
            )
            self.command_server.start()

        # Première collecte immédiate
        self.run_once()

        # Planifier les collectes suivantes
        schedule.every(self.config.scan_interval).seconds.do(self.run_once)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Arrêt de l'agent")
        finally:
            self.cleanup()

    def cleanup(self):
        """Nettoie les ressources."""
        if self.command_server:
            self.command_server.stop()
        self.docker_collector.close()
        self.http_client.close()


def main():
    """Point d'entrée principal."""
    agent = InfraMapperAgent()
    agent.run()


if __name__ == "__main__":
    main()
