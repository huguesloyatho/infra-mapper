"""Collecteur de métriques système pour l'agent Infra-Mapper."""

import logging
import os

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from models import HostMetricsReport

logger = logging.getLogger("infra-mapper-agent.metrics")


class MetricsCollector:
    """Collecteur de métriques système de l'hôte."""

    def __init__(self):
        """Initialise le collecteur de métriques."""
        if not PSUTIL_AVAILABLE:
            logger.warning("psutil non disponible - métriques host désactivées")
        self._last_net_io = None

    def collect_host_metrics(self) -> HostMetricsReport:
        """Collecte les métriques système de l'hôte."""
        if not PSUTIL_AVAILABLE:
            return HostMetricsReport()

        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()

            # Load average (Unix only)
            load_1m, load_5m, load_15m = None, None, None
            if hasattr(os, 'getloadavg'):
                load_1m, load_5m, load_15m = os.getloadavg()

            # Mémoire
            mem = psutil.virtual_memory()
            memory_total = int(mem.total / (1024 * 1024))  # MB
            memory_used = int(mem.used / (1024 * 1024))    # MB
            memory_percent = mem.percent

            # Disque (partition racine)
            disk = psutil.disk_usage('/')
            disk_total = int(disk.total / (1024 * 1024))   # MB
            disk_used = int(disk.used / (1024 * 1024))     # MB
            disk_percent = disk.percent

            # Réseau (total toutes interfaces)
            net_io = psutil.net_io_counters()
            network_rx_bytes = net_io.bytes_recv
            network_tx_bytes = net_io.bytes_sent

            return HostMetricsReport(
                cpu_percent=round(cpu_percent, 2),
                cpu_count=cpu_count,
                load_1m=round(load_1m, 2) if load_1m is not None else None,
                load_5m=round(load_5m, 2) if load_5m is not None else None,
                load_15m=round(load_15m, 2) if load_15m is not None else None,
                memory_total=memory_total,
                memory_used=memory_used,
                memory_percent=round(memory_percent, 2),
                disk_total=disk_total,
                disk_used=disk_used,
                disk_percent=round(disk_percent, 2),
                network_rx_bytes=network_rx_bytes,
                network_tx_bytes=network_tx_bytes,
            )

        except Exception as e:
            logger.error(f"Erreur collecte métriques host: {e}")
            return HostMetricsReport()
