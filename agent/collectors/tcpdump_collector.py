"""Collecteur de connexions réseau via tcpdump par conteneur."""

import subprocess
import re
import logging
import threading
import time
from typing import Optional
from dataclasses import dataclass
from enum import Enum

import docker

from models import NetworkConnection

logger = logging.getLogger(__name__)


class TcpdumpMode(str, Enum):
    """Mode de capture tcpdump."""
    INTERMITTENT = "intermittent"  # 30s de capture toutes les 10min
    ACTIVE = "active"  # Capture continue


@dataclass
class ContainerTarget:
    """Cible de capture pour un conteneur."""
    container_id: str
    container_name: str
    pid: int  # PID du processus principal du conteneur


class TcpdumpCollector:
    """Collecte les connexions réseau via tcpdump dans les namespaces des conteneurs."""

    def __init__(
        self,
        mode: TcpdumpMode = TcpdumpMode.INTERMITTENT,
        capture_duration: int = 30,
        capture_interval: int = 600,  # 10 minutes
        max_packets_per_container: int = 500,
    ):
        """
        Initialise le collecteur tcpdump.

        Args:
            mode: Mode de capture (intermittent ou active)
            capture_duration: Durée de capture en secondes (mode intermittent)
            capture_interval: Intervalle entre captures en secondes (mode intermittent)
            max_packets_per_container: Nombre max de paquets par conteneur
        """
        self.mode = mode
        self.capture_duration = capture_duration
        self.capture_interval = capture_interval
        self.max_packets_per_container = max_packets_per_container
        self._is_available = self._check_tcpdump()
        self._last_capture_time = 0
        self._cached_connections: list[NetworkConnection] = []
        self._capture_lock = threading.Lock()

        # Client Docker pour obtenir les PIDs des conteneurs
        try:
            self._docker_client = docker.DockerClient(base_url="unix:///var/run/docker.sock")
        except Exception as e:
            logger.warning(f"Impossible d'initialiser le client Docker: {e}")
            self._docker_client = None

    def _check_tcpdump(self) -> bool:
        """Vérifie si tcpdump et nsenter sont disponibles."""
        try:
            for cmd in ["tcpdump", "nsenter"]:
                result = subprocess.run(
                    ["which", cmd],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode != 0:
                    logger.warning(f"{cmd} non trouvé")
                    return False
            return True
        except Exception as e:
            logger.warning(f"Erreur vérification outils: {e}")
            return False

    def should_capture(self) -> bool:
        """Détermine si une capture doit être effectuée."""
        if self.mode == TcpdumpMode.ACTIVE:
            return True

        # Mode intermittent : vérifier l'intervalle
        now = time.time()
        if now - self._last_capture_time >= self.capture_interval:
            return True
        return False

    def collect(self, containers: list = None) -> list[NetworkConnection]:
        """
        Capture le trafic réseau des conteneurs.

        Args:
            containers: Liste de ContainerInfo avec id, name et status

        Returns:
            Liste de NetworkConnection avec source_method="tcpdump"
        """
        if not self._is_available:
            logger.debug("tcpdump/nsenter non disponible")
            return []

        if not containers:
            logger.debug("Aucun conteneur fourni pour capture tcpdump")
            return []

        # Vérifier si on doit capturer
        if not self.should_capture():
            remaining = self.capture_interval - (time.time() - self._last_capture_time)
            logger.debug(
                f"Capture tcpdump ignorée (mode {self.mode.value}, "
                f"prochaine dans {remaining:.0f}s)"
            )
            return self._cached_connections

        with self._capture_lock:
            self._last_capture_time = time.time()
            all_connections = []

            # Préparer les cibles de capture
            targets = self._prepare_targets(containers)

            if not targets:
                logger.debug("Aucun conteneur actif à capturer")
                return []

            logger.info(
                f"Capture tcpdump ({self.mode.value}): "
                f"{len(targets)} conteneurs, {self.capture_duration}s"
            )

            # Capturer en parallèle pour tous les conteneurs
            threads = []
            results = {}

            for target in targets:
                t = threading.Thread(
                    target=self._capture_container,
                    args=(target, results)
                )
                threads.append(t)
                t.start()

            # Attendre la fin des captures
            for t in threads:
                t.join(timeout=self.capture_duration + 10)

            # Collecter les résultats
            for container_id, connections in results.items():
                all_connections.extend(connections)

            logger.info(f"tcpdump: {len(all_connections)} connexions capturées sur {len(targets)} conteneurs")
            self._cached_connections = all_connections

        return all_connections

    def _prepare_targets(self, containers: list) -> list[ContainerTarget]:
        """Prépare les cibles de capture depuis les ContainerInfo."""
        targets = []

        for container in containers:
            # Vérifier que le conteneur est running
            if hasattr(container, 'status'):
                status = container.status.value if hasattr(container.status, 'value') else container.status
                if status != 'running':
                    continue

            # Obtenir le PID du conteneur via docker inspect
            container_id = container.id
            pid = self._get_container_pid(container_id)

            if pid:
                targets.append(ContainerTarget(
                    container_id=container_id,
                    container_name=container.name,
                    pid=pid
                ))

        return targets

    def _get_container_pid(self, container_id: str) -> Optional[int]:
        """Obtient le PID du processus principal d'un conteneur via l'API Docker."""
        if not self._docker_client:
            return None

        try:
            container = self._docker_client.containers.get(container_id)
            # L'attribut attrs contient les informations détaillées
            pid = container.attrs.get("State", {}).get("Pid", 0)
            if pid > 0:
                return pid
        except docker.errors.NotFound:
            logger.debug(f"Conteneur {container_id} non trouvé")
        except Exception as e:
            logger.debug(f"Erreur obtention PID pour {container_id}: {e}")
        return None

    def _capture_container(
        self,
        target: ContainerTarget,
        results: dict
    ):
        """Capture le trafic d'un conteneur via nsenter."""
        connections = []
        seen = set()

        try:
            # Utiliser nsenter pour entrer dans le namespace réseau du conteneur
            # puis exécuter tcpdump
            cmd = [
                "nsenter",
                "-t", str(target.pid),
                "-n",  # Network namespace
                "tcpdump",
                "-i", "any",
                "-nn",
                "-q",
                "-l",
                "-c", str(self.max_packets_per_container),
                "tcp or udp"
            ]

            logger.debug(f"Capture {target.container_name} (PID {target.pid})")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            try:
                stdout, stderr = process.communicate(timeout=self.capture_duration + 5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()

            # Parser la sortie
            for line in stdout.split("\n"):
                conn = self._parse_tcpdump_line(line, target.container_id)
                if conn:
                    key = (conn.local_ip, conn.local_port, conn.remote_ip, conn.remote_port, conn.protocol)
                    if key not in seen:
                        seen.add(key)
                        connections.append(conn)

            if connections:
                logger.debug(f"{target.container_name}: {len(connections)} connexions")

        except FileNotFoundError:
            logger.warning(f"nsenter/tcpdump non trouvé pour {target.container_name}")
        except PermissionError:
            logger.warning(f"Permission refusée pour {target.container_name}")
        except Exception as e:
            logger.debug(f"Erreur capture {target.container_name}: {e}")

        results[target.container_id] = connections

    def _parse_tcpdump_line(self, line: str, container_id: str) -> Optional[NetworkConnection]:
        """Parse une ligne de sortie tcpdump."""
        if not line or ">" not in line:
            return None

        try:
            if " IP " not in line and " IP6 " not in line:
                return None

            protocol = "tcp"
            if "UDP" in line or "udp" in line:
                protocol = "udp"

            # Pattern: src.port > dst.port:
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)\.(\d+)\s*>\s*(\d+\.\d+\.\d+\.\d+)\.(\d+):', line)
            if not match:
                return None

            src_ip = match.group(1)
            src_port = int(match.group(2))
            dst_ip = match.group(3)
            dst_port = int(match.group(4))

            # Ignorer localhost
            if src_ip.startswith("127.") and dst_ip.startswith("127."):
                return None

            return NetworkConnection(
                protocol=protocol,
                local_ip=src_ip,
                local_port=src_port,
                remote_ip=dst_ip,
                remote_port=dst_port,
                state="ESTABLISHED",
                pid=None,
                process_name=None,
                container_id=container_id,  # On connaît le conteneur !
                source_method="tcpdump",
            )

        except Exception as e:
            logger.debug(f"Erreur parsing ligne tcpdump: {e}")
            return None

    def is_available(self) -> bool:
        """Retourne True si tcpdump est disponible."""
        return self._is_available

    def get_mode(self) -> TcpdumpMode:
        """Retourne le mode de capture actuel."""
        return self.mode

    def get_next_capture_in(self) -> float:
        """Retourne le temps avant la prochaine capture (mode intermittent)."""
        if self.mode == TcpdumpMode.ACTIVE:
            return 0
        elapsed = time.time() - self._last_capture_time
        return max(0, self.capture_interval - elapsed)
