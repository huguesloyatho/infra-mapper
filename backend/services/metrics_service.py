"""Service de gestion des métriques time-series."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import HostMetrics, ContainerMetrics, Host, Container

logger = logging.getLogger(__name__)


class MetricsService:
    """Service pour la collecte et récupération des métriques."""

    # Rétention par défaut: 7 jours
    DEFAULT_RETENTION_DAYS = 7

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db

    # =========================================================================
    # Storage
    # =========================================================================

    async def store_host_metrics(self, host_id: str, metrics: dict) -> HostMetrics:
        """
        Stocke les métriques d'un host.

        Args:
            host_id: ID du host
            metrics: Dictionnaire de métriques:
                - cpu_percent, cpu_count, load_1m, load_5m, load_15m
                - memory_total, memory_used, memory_percent
                - disk_total, disk_used, disk_percent
                - network_rx_bytes, network_tx_bytes

        Returns:
            HostMetrics créé
        """
        host_metrics = HostMetrics(
            host_id=host_id,
            timestamp=datetime.utcnow(),
            cpu_percent=metrics.get("cpu_percent"),
            cpu_count=metrics.get("cpu_count"),
            load_1m=int(metrics.get("load_1m", 0) * 100) if metrics.get("load_1m") else None,
            load_5m=int(metrics.get("load_5m", 0) * 100) if metrics.get("load_5m") else None,
            load_15m=int(metrics.get("load_15m", 0) * 100) if metrics.get("load_15m") else None,
            memory_total=metrics.get("memory_total"),
            memory_used=metrics.get("memory_used"),
            memory_percent=metrics.get("memory_percent"),
            disk_total=metrics.get("disk_total"),
            disk_used=metrics.get("disk_used"),
            disk_percent=metrics.get("disk_percent"),
            network_rx_bytes=metrics.get("network_rx_bytes"),
            network_tx_bytes=metrics.get("network_tx_bytes"),
        )

        self.db.add(host_metrics)
        await self.db.flush()

        logger.debug(f"Métriques host stockées: {host_id}")
        return host_metrics

    async def store_container_metrics(
        self,
        host_id: str,
        container_id: str,
        metrics: dict
    ) -> ContainerMetrics:
        """
        Stocke les métriques d'un container.

        Args:
            host_id: ID du host
            container_id: ID du container (format: host_id:short_id)
            metrics: Dictionnaire de métriques

        Returns:
            ContainerMetrics créé
        """
        container_metrics = ContainerMetrics(
            container_id=container_id,
            host_id=host_id,
            timestamp=datetime.utcnow(),
            cpu_percent=int(metrics.get("cpu_percent", 0) * 100) if metrics.get("cpu_percent") else None,
            memory_used=metrics.get("memory_used"),
            memory_limit=metrics.get("memory_limit"),
            memory_percent=metrics.get("memory_percent"),
            network_rx_bytes=metrics.get("network_rx_bytes"),
            network_tx_bytes=metrics.get("network_tx_bytes"),
            disk_read_bytes=metrics.get("disk_read_bytes"),
            disk_write_bytes=metrics.get("disk_write_bytes"),
            pids=metrics.get("pids"),
        )

        self.db.add(container_metrics)
        await self.db.flush()

        logger.debug(f"Métriques container stockées: {container_id}")
        return container_metrics

    async def store_bulk_container_metrics(
        self,
        host_id: str,
        containers_metrics: List[dict]
    ) -> int:
        """
        Stocke les métriques de plusieurs containers.

        Args:
            host_id: ID du host
            containers_metrics: Liste de {container_id, metrics}

        Returns:
            Nombre de métriques stockées
        """
        timestamp = datetime.utcnow()
        count = 0

        for item in containers_metrics:
            container_id = item.get("container_id")
            metrics = item.get("metrics", {})

            if not container_id:
                continue

            # Format container_id: host_id:short_id
            full_container_id = f"{host_id}:{container_id}"

            container_metrics = ContainerMetrics(
                container_id=full_container_id,
                host_id=host_id,
                timestamp=timestamp,
                cpu_percent=int(metrics.get("cpu_percent", 0) * 100) if metrics.get("cpu_percent") else None,
                memory_used=metrics.get("memory_used"),
                memory_limit=metrics.get("memory_limit"),
                memory_percent=metrics.get("memory_percent"),
                network_rx_bytes=metrics.get("network_rx_bytes"),
                network_tx_bytes=metrics.get("network_tx_bytes"),
                disk_read_bytes=metrics.get("disk_read_bytes"),
                disk_write_bytes=metrics.get("disk_write_bytes"),
                pids=metrics.get("pids"),
            )

            self.db.add(container_metrics)
            count += 1

        await self.db.flush()
        logger.debug(f"Métriques bulk stockées: {count} containers pour {host_id}")
        return count

    # =========================================================================
    # Retrieval
    # =========================================================================

    async def get_host_metrics(
        self,
        host_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        interval_minutes: int = 5,
    ) -> List[dict]:
        """
        Récupère les métriques d'un host avec agrégation optionnelle.

        Args:
            host_id: ID du host
            start_time: Début de la période (défaut: 1h)
            end_time: Fin de la période (défaut: maintenant)
            interval_minutes: Intervalle d'agrégation

        Returns:
            Liste de métriques
        """
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(hours=1)

        query = select(HostMetrics).where(
            and_(
                HostMetrics.host_id == host_id,
                HostMetrics.timestamp >= start_time,
                HostMetrics.timestamp <= end_time,
            )
        ).order_by(HostMetrics.timestamp.asc())

        result = await self.db.execute(query)
        metrics = result.scalars().all()

        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "cpu_percent": m.cpu_percent,
                "cpu_count": m.cpu_count,
                "load_1m": m.load_1m / 100 if m.load_1m else None,
                "load_5m": m.load_5m / 100 if m.load_5m else None,
                "load_15m": m.load_15m / 100 if m.load_15m else None,
                "memory_total": m.memory_total,
                "memory_used": m.memory_used,
                "memory_percent": m.memory_percent,
                "disk_total": m.disk_total,
                "disk_used": m.disk_used,
                "disk_percent": m.disk_percent,
                "network_rx_bytes": m.network_rx_bytes,
                "network_tx_bytes": m.network_tx_bytes,
            }
            for m in metrics
        ]

    async def get_container_metrics(
        self,
        container_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[dict]:
        """
        Récupère les métriques d'un container.

        Args:
            container_id: ID du container
            start_time: Début de la période
            end_time: Fin de la période

        Returns:
            Liste de métriques
        """
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(hours=1)

        query = select(ContainerMetrics).where(
            and_(
                ContainerMetrics.container_id == container_id,
                ContainerMetrics.timestamp >= start_time,
                ContainerMetrics.timestamp <= end_time,
            )
        ).order_by(ContainerMetrics.timestamp.asc())

        result = await self.db.execute(query)
        metrics = result.scalars().all()

        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "cpu_percent": m.cpu_percent / 100 if m.cpu_percent else None,
                "memory_used": m.memory_used,
                "memory_limit": m.memory_limit,
                "memory_percent": m.memory_percent,
                "network_rx_bytes": m.network_rx_bytes,
                "network_tx_bytes": m.network_tx_bytes,
                "disk_read_bytes": m.disk_read_bytes,
                "disk_write_bytes": m.disk_write_bytes,
                "pids": m.pids,
            }
            for m in metrics
        ]

    async def get_host_latest_metrics(self, host_id: str) -> Optional[dict]:
        """Récupère les dernières métriques d'un host."""
        query = select(HostMetrics).where(
            HostMetrics.host_id == host_id
        ).order_by(HostMetrics.timestamp.desc()).limit(1)

        result = await self.db.execute(query)
        m = result.scalar_one_or_none()

        if not m:
            return None

        return {
            "timestamp": m.timestamp.isoformat(),
            "cpu_percent": m.cpu_percent,
            "memory_percent": m.memory_percent,
            "disk_percent": m.disk_percent,
            "load_1m": m.load_1m / 100 if m.load_1m else None,
        }

    async def get_container_latest_metrics(self, container_id: str) -> Optional[dict]:
        """Récupère les dernières métriques d'un container."""
        query = select(ContainerMetrics).where(
            ContainerMetrics.container_id == container_id
        ).order_by(ContainerMetrics.timestamp.desc()).limit(1)

        result = await self.db.execute(query)
        m = result.scalar_one_or_none()

        if not m:
            return None

        return {
            "timestamp": m.timestamp.isoformat(),
            "cpu_percent": m.cpu_percent / 100 if m.cpu_percent else None,
            "memory_used": m.memory_used,
            "memory_percent": m.memory_percent,
        }

    # =========================================================================
    # Aggregation / Analytics
    # =========================================================================

    async def get_host_summary(
        self,
        host_id: str,
        period_hours: int = 24
    ) -> dict:
        """
        Récupère un résumé des métriques d'un host sur une période.

        Returns:
            {avg_cpu, max_cpu, avg_memory, max_memory, avg_disk, etc.}
        """
        cutoff = datetime.utcnow() - timedelta(hours=period_hours)

        query = select(
            func.avg(HostMetrics.cpu_percent).label("avg_cpu"),
            func.max(HostMetrics.cpu_percent).label("max_cpu"),
            func.avg(HostMetrics.memory_percent).label("avg_memory"),
            func.max(HostMetrics.memory_percent).label("max_memory"),
            func.avg(HostMetrics.disk_percent).label("avg_disk"),
            func.max(HostMetrics.disk_percent).label("max_disk"),
            func.count().label("sample_count"),
        ).where(
            and_(
                HostMetrics.host_id == host_id,
                HostMetrics.timestamp >= cutoff,
            )
        )

        result = await self.db.execute(query)
        row = result.one()

        return {
            "period_hours": period_hours,
            "sample_count": row.sample_count,
            "cpu": {
                "avg": round(row.avg_cpu, 1) if row.avg_cpu else None,
                "max": row.max_cpu,
            },
            "memory": {
                "avg": round(row.avg_memory, 1) if row.avg_memory else None,
                "max": row.max_memory,
            },
            "disk": {
                "avg": round(row.avg_disk, 1) if row.avg_disk else None,
                "max": row.max_disk,
            },
        }

    async def get_all_hosts_current_metrics(self) -> List[dict]:
        """
        Récupère les métriques actuelles de tous les hosts.

        Returns:
            Liste de {host_id, hostname, cpu_percent, memory_percent, disk_percent}
        """
        # Sous-requête pour obtenir le dernier timestamp par host
        subquery = select(
            HostMetrics.host_id,
            func.max(HostMetrics.timestamp).label("max_ts")
        ).group_by(HostMetrics.host_id).subquery()

        # Jointure pour récupérer les métriques correspondantes
        query = select(
            HostMetrics, Host.hostname
        ).join(
            subquery,
            and_(
                HostMetrics.host_id == subquery.c.host_id,
                HostMetrics.timestamp == subquery.c.max_ts,
            )
        ).join(
            Host, Host.id == HostMetrics.host_id
        )

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                "host_id": m.host_id,
                "hostname": hostname,
                "timestamp": m.timestamp.isoformat(),
                "cpu_percent": m.cpu_percent,
                "memory_percent": m.memory_percent,
                "disk_percent": m.disk_percent,
                "load_1m": m.load_1m / 100 if m.load_1m else None,
            }
            for m, hostname in rows
        ]

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def cleanup_old_metrics(self, retention_days: int = None) -> dict:
        """
        Supprime les métriques plus anciennes que retention_days.

        Returns:
            {host_metrics_deleted, container_metrics_deleted}
        """
        if retention_days is None:
            retention_days = self.DEFAULT_RETENTION_DAYS

        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        # Supprimer les métriques host
        result1 = await self.db.execute(
            delete(HostMetrics).where(HostMetrics.timestamp < cutoff)
        )
        host_deleted = result1.rowcount

        # Supprimer les métriques container
        result2 = await self.db.execute(
            delete(ContainerMetrics).where(ContainerMetrics.timestamp < cutoff)
        )
        container_deleted = result2.rowcount

        await self.db.commit()

        logger.info(
            f"Nettoyage métriques: {host_deleted} host, {container_deleted} container "
            f"(rétention: {retention_days} jours)"
        )

        return {
            "host_metrics_deleted": host_deleted,
            "container_metrics_deleted": container_deleted,
            "retention_days": retention_days,
        }

    # =========================================================================
    # Export (pour Grafana/Prometheus)
    # =========================================================================

    async def export_prometheus_metrics(self) -> str:
        """
        Exporte les métriques au format Prometheus.

        Returns:
            Texte au format Prometheus exposition
        """
        lines = []

        # Récupérer les métriques actuelles de tous les hosts
        hosts_metrics = await self.get_all_hosts_current_metrics()

        for m in hosts_metrics:
            host_id = m["host_id"]
            hostname = m["hostname"]
            labels = f'host_id="{host_id}",hostname="{hostname}"'

            if m["cpu_percent"] is not None:
                lines.append(f'infra_host_cpu_percent{{{labels}}} {m["cpu_percent"]}')
            if m["memory_percent"] is not None:
                lines.append(f'infra_host_memory_percent{{{labels}}} {m["memory_percent"]}')
            if m["disk_percent"] is not None:
                lines.append(f'infra_host_disk_percent{{{labels}}} {m["disk_percent"]}')
            if m["load_1m"] is not None:
                lines.append(f'infra_host_load_1m{{{labels}}} {m["load_1m"]}')

        return "\n".join(lines)
