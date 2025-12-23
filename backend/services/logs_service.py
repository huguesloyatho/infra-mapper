"""Service pour la gestion des logs de containers."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ContainerLog, Container, Host
from config import get_settings

logger = logging.getLogger(__name__)


def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convertit un datetime timezone-aware en naive UTC."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Convertir en UTC puis supprimer le tzinfo
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


settings = get_settings()


class LogsService:
    """Service pour requêter et gérer les logs de containers."""

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db

    async def get_container_logs(
        self,
        container_id: str,
        limit: int = 500,
        offset: int = 0,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        search: Optional[str] = None,
        stream: Optional[str] = None,
    ) -> Tuple[List[ContainerLog], int]:
        """
        Récupère les logs d'un container avec pagination.

        Args:
            container_id: ID du container
            limit: Nombre max de logs
            offset: Offset pour pagination
            since: Logs depuis cette date
            until: Logs jusqu'à cette date
            search: Recherche dans le message
            stream: Filtrer par stream (stdout/stderr)

        Returns:
            Tuple (logs, total)
        """
        query = select(ContainerLog).where(ContainerLog.container_id == container_id)

        if since:
            query = query.where(ContainerLog.timestamp >= since)
        if until:
            query = query.where(ContainerLog.timestamp <= until)
        if search:
            query = query.where(ContainerLog.message.ilike(f"%{search}%"))
        if stream:
            query = query.where(ContainerLog.stream == stream)

        # Compter le total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Récupérer la page
        query = query.order_by(ContainerLog.timestamp.desc())
        query = query.offset(offset).limit(limit)

        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    async def get_host_logs(
        self,
        host_id: str,
        limit: int = 500,
        since: Optional[datetime] = None,
    ) -> List[ContainerLog]:
        """
        Récupère tous les logs d'un hôte.

        Args:
            host_id: ID de l'hôte
            limit: Nombre max de logs
            since: Logs depuis cette date

        Returns:
            Liste des logs
        """
        query = select(ContainerLog).where(ContainerLog.host_id == host_id)

        if since:
            query = query.where(ContainerLog.timestamp >= since)

        query = query.order_by(ContainerLog.timestamp.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def store_logs(self, host_id: str, logs: List[dict]) -> int:
        """
        Stocke les logs en base.

        Args:
            host_id: ID de l'hôte
            logs: Liste des logs à stocker

        Returns:
            Nombre de logs stockés
        """
        stored = 0
        for log in logs:
            try:
                # Parser le timestamp
                ts_str = log.get("timestamp", "")
                if ts_str:
                    # Format ISO ou autre
                    if "T" in ts_str:
                        timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        # Convertir en naive UTC pour la base de données
                        timestamp = to_naive_utc(timestamp)
                    else:
                        timestamp = datetime.utcnow()
                else:
                    timestamp = datetime.utcnow()

                # Tronquer le message si trop long
                message = log.get("message", "")[:10000]

                db_log = ContainerLog(
                    container_id=f"{host_id}:{log.get('container_id', 'unknown')}",
                    host_id=host_id,
                    timestamp=timestamp,
                    stream=log.get("stream", "stdout"),
                    message=message,
                )
                self.db.add(db_log)
                stored += 1

            except Exception as e:
                logger.debug(f"Erreur stockage log: {e}")
                continue

        if stored > 0:
            await self.db.commit()

        return stored

    async def cleanup_old_logs(self, days: Optional[int] = None) -> int:
        """
        Supprime les logs plus vieux que N jours.

        Args:
            days: Nombre de jours de rétention (défaut: settings)

        Returns:
            Nombre de logs supprimés
        """
        retention_days = days or settings.logs_retention_days
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        # Compter avant suppression
        count_query = select(func.count()).where(ContainerLog.timestamp < cutoff)
        count_result = await self.db.execute(count_query)
        count = count_result.scalar() or 0

        if count > 0:
            await self.db.execute(
                delete(ContainerLog).where(ContainerLog.timestamp < cutoff)
            )
            await self.db.commit()
            logger.info(f"Supprimé {count} logs plus vieux que {retention_days} jours")

        return count

    async def get_logs_stats(self) -> dict:
        """
        Retourne des statistiques sur les logs.

        Returns:
            Dictionnaire de statistiques
        """
        # Total des logs
        total_query = select(func.count()).select_from(ContainerLog)
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # Logs par stream
        stdout_query = select(func.count()).where(ContainerLog.stream == "stdout")
        stdout_result = await self.db.execute(stdout_query)
        stdout_count = stdout_result.scalar() or 0

        stderr_query = select(func.count()).where(ContainerLog.stream == "stderr")
        stderr_result = await self.db.execute(stderr_query)
        stderr_count = stderr_result.scalar() or 0

        # Plus ancien log
        oldest_query = select(func.min(ContainerLog.timestamp))
        oldest_result = await self.db.execute(oldest_query)
        oldest = oldest_result.scalar()

        # Plus récent log
        newest_query = select(func.max(ContainerLog.timestamp))
        newest_result = await self.db.execute(newest_query)
        newest = newest_result.scalar()

        return {
            "total": total,
            "stdout": stdout_count,
            "stderr": stderr_count,
            "oldest": oldest.isoformat() if oldest else None,
            "newest": newest.isoformat() if newest else None,
        }

    async def get_container_info(self, container_id: str) -> Optional[dict]:
        """
        Récupère les infos d'un container pour enrichir les logs.

        Args:
            container_id: ID du container

        Returns:
            Infos du container ou None
        """
        result = await self.db.execute(
            select(Container).where(Container.id == container_id)
        )
        container = result.scalar_one_or_none()

        if not container:
            return None

        # Récupérer le host
        host_result = await self.db.execute(
            select(Host).where(Host.id == container.host_id)
        )
        host = host_result.scalar_one_or_none()

        return {
            "container_id": container.id,
            "container_name": container.name,
            "host_id": container.host_id,
            "host_name": host.hostname if host else "unknown",
        }
