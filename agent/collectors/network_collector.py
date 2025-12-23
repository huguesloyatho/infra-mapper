"""Collecteur de connexions réseau."""

import subprocess
import re
import os
import logging
import struct
import socket
from typing import Optional

from models import NetworkConnection

logger = logging.getLogger(__name__)


class NetworkCollector:
    """Collecte les connexions réseau actives via /proc/net et ss."""

    # États TCP (de /proc/net/tcp)
    TCP_STATES = {
        '01': 'ESTAB',
        '02': 'SYN-SENT',
        '03': 'SYN-RECV',
        '04': 'FIN-WAIT-1',
        '05': 'FIN-WAIT-2',
        '06': 'TIME-WAIT',
        '07': 'CLOSE',
        '08': 'CLOSE-WAIT',
        '09': 'LAST-ACK',
        '0A': 'LISTEN',
        '0B': 'CLOSING',
    }

    def __init__(self):
        """Initialise le collecteur réseau."""
        self._pid_to_container: dict[int, str] = {}
        self._inode_to_pid: dict[int, int] = {}
        self._build_pid_container_map()

    def _build_pid_container_map(self):
        """Construit le mapping PID -> container_id via /proc/*/cgroup."""
        self._pid_to_container = {}

        try:
            for pid_dir in os.listdir("/proc"):
                if not pid_dir.isdigit():
                    continue

                pid = int(pid_dir)
                cgroup_path = f"/proc/{pid}/cgroup"

                try:
                    with open(cgroup_path, "r") as f:
                        content = f.read()

                    patterns = [
                        r'/docker/([a-f0-9]{12,64})',
                        r'docker-([a-f0-9]{12,64})\.scope',
                        r'/containerd/([a-f0-9]{12,64})',
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, content)
                        if match:
                            container_id = match.group(1)[:12]
                            self._pid_to_container[pid] = container_id
                            break

                except (FileNotFoundError, PermissionError):
                    continue

        except Exception as e:
            logger.debug(f"Erreur construction mapping PID->container: {e}")

    def _build_inode_to_pid_map(self):
        """Construit le mapping inode socket -> PID via /proc/*/fd."""
        self._inode_to_pid = {}

        try:
            for pid_dir in os.listdir("/proc"):
                if not pid_dir.isdigit():
                    continue

                pid = int(pid_dir)
                fd_dir = f"/proc/{pid}/fd"

                try:
                    for fd in os.listdir(fd_dir):
                        try:
                            link = os.readlink(f"{fd_dir}/{fd}")
                            # Format: socket:[12345]
                            if link.startswith("socket:["):
                                inode = int(link[8:-1])
                                self._inode_to_pid[inode] = pid
                        except (FileNotFoundError, PermissionError, ValueError):
                            continue
                except (FileNotFoundError, PermissionError):
                    continue

        except Exception as e:
            logger.debug(f"Erreur construction mapping inode->PID: {e}")

    def collect_connections(self) -> list[NetworkConnection]:
        """Collecte toutes les connexions réseau actives."""
        # Rafraîchir le mapping PID -> container
        self._build_pid_container_map()

        connections = []

        # Collecter les connexions de chaque container en lisant son namespace réseau
        container_connections = self._collect_container_connections()
        connections.extend(container_connections)

        # Collecter aussi les connexions de l'hôte (docker-proxy, etc.)
        host_connections = self._collect_host_connections()
        connections.extend(host_connections)

        logger.debug(f"Collecte totale: {len(connections)} connexions ({len(container_connections)} container, {len(host_connections)} host)")

        return connections

    def _get_containers_by_netns(self) -> dict[str, tuple[int, str]]:
        """Retourne un mapping net_namespace -> (representative_pid, container_id)."""
        netns_to_container = {}

        for pid, container_id in self._pid_to_container.items():
            try:
                net_ns = os.readlink(f"/proc/{pid}/ns/net")
                # Garder le premier PID trouvé pour chaque namespace
                if net_ns not in netns_to_container:
                    netns_to_container[net_ns] = (pid, container_id)
            except (FileNotFoundError, PermissionError):
                continue

        return netns_to_container

    def _collect_container_connections(self) -> list[NetworkConnection]:
        """Collecte les connexions de tous les containers en lisant leurs namespaces."""
        connections = []

        # Obtenir un PID représentatif pour chaque namespace de container unique
        netns_map = self._get_containers_by_netns()

        for net_ns, (pid, container_id) in netns_map.items():
            for protocol in ["tcp", "udp"]:
                proc_file = f"/proc/{pid}/net/{protocol}"
                try:
                    with open(proc_file, "r") as f:
                        lines = f.readlines()[1:]  # Skip header

                    for line in lines:
                        conn = self._parse_proc_net_line(line, protocol, container_id)
                        if conn:
                            connections.append(conn)

                except (FileNotFoundError, PermissionError):
                    continue
                except Exception as e:
                    logger.debug(f"Erreur parsing {proc_file}: {e}")

        return connections

    def _collect_host_connections(self) -> list[NetworkConnection]:
        """Collecte les connexions du namespace réseau de l'hôte."""
        connections = []

        # Utiliser PID 1 (init) pour accéder au namespace de l'hôte
        for protocol in ["tcp", "udp"]:
            proc_file = f"/proc/1/net/{protocol}"
            try:
                with open(proc_file, "r") as f:
                    lines = f.readlines()[1:]

                for line in lines:
                    # Pour les connexions hôte, pas de container_id
                    conn = self._parse_proc_net_line(line, protocol, None)
                    if conn:
                        connections.append(conn)

            except (FileNotFoundError, PermissionError):
                continue
            except Exception as e:
                logger.debug(f"Erreur parsing {proc_file}: {e}")

        return connections

    def _parse_proc_net_line(self, line: str, protocol: str, container_id: Optional[str] = None) -> Optional[NetworkConnection]:
        """Parse une ligne de /proc/net/tcp ou /proc/net/udp."""
        try:
            parts = line.split()
            if len(parts) < 10:
                return None

            # Format: sl local_address rem_address st tx_queue:rx_queue tr:tm->when retrnsmt uid timeout inode
            local_addr = parts[1]
            remote_addr = parts[2]
            state_hex = parts[3]

            # Parser les adresses (format hex: IP:PORT)
            local_ip, local_port = self._parse_hex_address(local_addr)
            remote_ip, remote_port = self._parse_hex_address(remote_addr)

            if not local_ip:
                return None

            # Ignorer les connexions localhost internes (127.0.0.11 est le DNS Docker)
            if local_ip.startswith("127.") and remote_ip and remote_ip.startswith("127."):
                return None

            # Convertir l'état
            state = self.TCP_STATES.get(state_hex, state_hex) if protocol == "tcp" else "UNCONN"

            return NetworkConnection(
                protocol=protocol,
                local_ip=local_ip,
                local_port=local_port,
                remote_ip=remote_ip or "0.0.0.0",
                remote_port=remote_port or 0,
                state=state,
                pid=None,  # Pas de PID car on lit directement le namespace
                process_name=None,
                container_id=container_id,
            )

        except Exception as e:
            logger.debug(f"Erreur parsing ligne /proc/net: {e}")
            return None

    def _parse_hex_address(self, hex_addr: str) -> tuple[Optional[str], Optional[int]]:
        """Parse une adresse au format hex (IP:PORT) de /proc/net."""
        try:
            ip_hex, port_hex = hex_addr.split(":")
            port = int(port_hex, 16)

            # Convertir l'IP hex en notation pointée (little-endian sur x86)
            ip_int = int(ip_hex, 16)
            ip = socket.inet_ntoa(struct.pack("<I", ip_int))

            return ip, port
        except Exception:
            return None, None

    def _run_ss(self, protocol: str) -> list[NetworkConnection]:
        """Exécute ss et parse les résultats."""
        connections = []

        try:
            # ss -tunap : TCP/UDP, numérique, all, processus
            flag = "-t" if protocol == "tcp" else "-u"
            cmd = ["ss", flag, "-n", "-a", "-p"]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.warning(f"ss a retourné le code {result.returncode}")
                return connections

            lines = result.stdout.strip().split("\n")[1:]  # Skip header

            for line in lines:
                conn = self._parse_ss_line(line, protocol)
                if conn:
                    connections.append(conn)

        except subprocess.TimeoutExpired:
            logger.error("Timeout lors de l'exécution de ss")
        except FileNotFoundError:
            logger.error("Commande ss non trouvée")
        except Exception as e:
            logger.error(f"Erreur lors de la collecte réseau: {e}")

        return connections

    def _parse_ss_line(self, line: str, protocol: str) -> Optional[NetworkConnection]:
        """Parse une ligne de sortie ss."""
        try:
            # Format: State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
            parts = line.split()

            if len(parts) < 5:
                return None

            state = parts[0]
            local_addr = parts[3]
            peer_addr = parts[4]

            # Parser les adresses
            local_ip, local_port = self._parse_address(local_addr)
            remote_ip, remote_port = self._parse_address(peer_addr)

            if not all([local_ip, local_port]):
                return None

            # Parser le processus si présent
            pid = None
            process_name = None
            container_id = None

            if len(parts) > 5:
                process_info = " ".join(parts[5:])
                pid, process_name = self._parse_process(process_info)

                # Mapper le PID au container_id
                if pid:
                    container_id = self._pid_to_container.get(pid)

            return NetworkConnection(
                protocol=protocol,
                local_ip=local_ip,
                local_port=local_port,
                remote_ip=remote_ip or "0.0.0.0",
                remote_port=remote_port or 0,
                state=state,
                pid=pid,
                process_name=process_name,
                container_id=container_id,
            )
        except Exception as e:
            logger.debug(f"Erreur parsing ligne ss: {line} - {e}")
            return None

    def _parse_address(self, addr: str) -> tuple[Optional[str], Optional[int]]:
        """Parse une adresse IP:port."""
        try:
            # Gérer IPv6: [::]:port ou [::1]:port
            if addr.startswith("["):
                match = re.match(r'\[([^\]]+)\]:(\d+)', addr)
                if match:
                    return match.group(1), int(match.group(2))
                return None, None

            # IPv4: ip:port
            if ":" in addr:
                # Le dernier : sépare le port
                last_colon = addr.rfind(":")
                ip = addr[:last_colon]
                port = addr[last_colon + 1:]

                # Gérer le cas "*" pour 0.0.0.0
                if ip == "*":
                    ip = "0.0.0.0"

                return ip, int(port) if port != "*" else 0

            return None, None
        except (ValueError, AttributeError):
            return None, None

    def _parse_process(self, process_info: str) -> tuple[Optional[int], Optional[str]]:
        """Parse les informations du processus."""
        try:
            # Format: users:(("docker-proxy",pid=1234,fd=5))
            pid_match = re.search(r'pid=(\d+)', process_info)
            name_match = re.search(r'\("([^"]+)"', process_info)

            pid = int(pid_match.group(1)) if pid_match else None
            name = name_match.group(1) if name_match else None

            return pid, name
        except Exception:
            return None, None

    def get_local_ips(self) -> list[str]:
        """Récupère les IPs locales de la machine."""
        ips = []

        try:
            import netifaces

            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)

                # IPv4
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        ip = addr.get("addr")
                        if ip and not ip.startswith("127."):
                            ips.append(ip)

        except ImportError:
            # Fallback sans netifaces
            try:
                result = subprocess.run(
                    ["hostname", "-I"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    ips = result.stdout.strip().split()
            except Exception as e:
                logger.warning(f"Impossible de récupérer les IPs: {e}")

        return ips
