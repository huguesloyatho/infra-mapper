"""Service de monitoring de santé des agents."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Host

logger = logging.getLogger(__name__)

# Seuils de détection de dégradation
DEFAULT_REPORT_INTERVAL = 30  # Intervalle par défaut en secondes
DEGRADED_THRESHOLD_FACTOR = 2.0  # Facteur pour considérer un délai comme dégradé
UNHEALTHY_THRESHOLD_FACTOR = 5.0  # Facteur pour considérer l'agent comme unhealthy
MAX_CONSECUTIVE_FAILURES = 3  # Nombre d'échecs consécutifs avant dégradation
# Rapport lent = prend plus de 90% de l'intervalle de rapport (calculé dynamiquement)
SLOW_REPORT_THRESHOLD_FACTOR = 0.9


class AgentHealthService:
    """Service de monitoring de santé des agents."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_agent_health(
        self,
        host_id: str,
        agent_version: Optional[str] = None,
        report_interval: Optional[int] = None,
        report_duration_ms: Optional[int] = None,
        uptime_seconds: Optional[int] = None,
        error: Optional[str] = None,
        command_port: Optional[int] = None,
    ) -> Optional[Host]:
        """
        Met à jour les informations de santé d'un agent après réception d'un rapport.

        Args:
            host_id: ID de l'hôte
            agent_version: Version de l'agent
            report_interval: Intervalle de rapport configuré (secondes)
            report_duration_ms: Durée de génération du rapport (millisecondes)
            uptime_seconds: Uptime de l'agent
            error: Message d'erreur si le rapport contient une erreur
            command_port: Port du serveur de commandes de l'agent

        Returns:
            Host mis à jour ou None si non trouvé
        """
        result = await self.db.execute(
            select(Host).where(Host.id == host_id)
        )
        host = result.scalar_one_or_none()

        if not host:
            return None

        now = datetime.utcnow()

        # Mettre à jour les métadonnées agent
        if agent_version:
            host.agent_version = agent_version
        if report_interval:
            host.report_interval = report_interval
        if uptime_seconds is not None:
            host.uptime_seconds = uptime_seconds
        if command_port is not None:
            host.command_port = command_port

        # Mettre à jour les durées de rapport
        if report_duration_ms is not None:
            host.last_report_duration = report_duration_ms
            # Calculer la moyenne mobile
            if host.avg_report_duration:
                host.avg_report_duration = int(
                    (host.avg_report_duration * 0.8) + (report_duration_ms * 0.2)
                )
            else:
                host.avg_report_duration = report_duration_ms

        # Incrémenter le compteur de rapports
        host.reports_count = (host.reports_count or 0) + 1

        # Gérer les erreurs
        if error:
            host.consecutive_failures = (host.consecutive_failures or 0) + 1
            host.errors_count = (host.errors_count or 0) + 1
            host.last_error = error
            host.last_error_at = now
        else:
            # Reset des échecs consécutifs si rapport réussi
            host.consecutive_failures = 0

        # Calculer le nouveau statut de santé
        host.agent_health = self._calculate_health_status(host, report_duration_ms)
        host.last_seen = now
        host.is_online = True

        await self.db.commit()
        await self.db.refresh(host)

        return host

    def _calculate_health_status(
        self,
        host: Host,
        report_duration_ms: Optional[int] = None
    ) -> str:
        """
        Calcule le statut de santé basé sur différents critères.

        Critères de dégradation:
        - Échecs consécutifs >= MAX_CONSECUTIVE_FAILURES
        - Durée du rapport > 80% de l'intervalle de rapport
        - Délai entre rapports > expected_interval * DEGRADED_THRESHOLD_FACTOR
        """
        # Trop d'échecs consécutifs
        if (host.consecutive_failures or 0) >= MAX_CONSECUTIVE_FAILURES:
            return "degraded"

        # Rapport trop lent (prend plus de 80% de l'intervalle)
        if report_duration_ms:
            report_interval_ms = (host.report_interval or DEFAULT_REPORT_INTERVAL) * 1000
            slow_threshold_ms = report_interval_ms * SLOW_REPORT_THRESHOLD_FACTOR
            if report_duration_ms > slow_threshold_ms:
                return "degraded"

        # Pas assez de données pour juger
        if (host.reports_count or 0) < 3:
            return "unknown"

        return "healthy"

    async def check_all_agents_health(self) -> Dict[str, Any]:
        """
        Vérifie la santé de tous les agents et met à jour leur statut.
        Cette méthode devrait être appelée périodiquement (cron/scheduler).

        Returns:
            Dict avec les statistiques de santé
        """
        now = datetime.utcnow()
        stats = {
            "total": 0,
            "healthy": 0,
            "degraded": 0,
            "unhealthy": 0,
            "unknown": 0,
            "offline": 0,
            "updated_hosts": []
        }

        result = await self.db.execute(select(Host))
        hosts = result.scalars().all()

        for host in hosts:
            stats["total"] += 1
            expected_interval = host.report_interval or DEFAULT_REPORT_INTERVAL

            # Calculer le délai depuis le dernier rapport
            if host.last_seen:
                seconds_since_last_report = (now - host.last_seen).total_seconds()
            else:
                seconds_since_last_report = float('inf')

            new_health = host.agent_health or "unknown"
            new_is_online = host.is_online

            # Vérifier si l'agent est hors ligne
            if seconds_since_last_report > expected_interval * UNHEALTHY_THRESHOLD_FACTOR:
                new_health = "unhealthy"
                new_is_online = False
                stats["offline"] += 1
            elif seconds_since_last_report > expected_interval * DEGRADED_THRESHOLD_FACTOR:
                new_health = "degraded"
                stats["degraded"] += 1
            else:
                # Comptabiliser le statut actuel
                if host.agent_health == "healthy":
                    stats["healthy"] += 1
                elif host.agent_health == "degraded":
                    stats["degraded"] += 1
                elif host.agent_health == "unhealthy":
                    stats["unhealthy"] += 1
                else:
                    stats["unknown"] += 1

            # Mettre à jour si changement
            if new_health != host.agent_health or new_is_online != host.is_online:
                old_health = host.agent_health
                host.agent_health = new_health
                host.is_online = new_is_online
                stats["updated_hosts"].append({
                    "host_id": host.id,
                    "hostname": host.hostname,
                    "old_health": old_health,
                    "new_health": new_health,
                    "is_online": new_is_online,
                })

        await self.db.commit()

        return stats

    async def get_agents_health_summary(self) -> Dict[str, Any]:
        """
        Retourne un résumé de la santé de tous les agents.

        Returns:
            Dict avec les statistiques et la liste des agents par statut
        """
        result = await self.db.execute(select(Host))
        hosts = result.scalars().all()

        now = datetime.utcnow()
        summary = {
            "total": len(hosts),
            "by_status": {
                "healthy": [],
                "degraded": [],
                "unhealthy": [],
                "unknown": [],
            },
            "stats": {
                "healthy": 0,
                "degraded": 0,
                "unhealthy": 0,
                "unknown": 0,
                "online": 0,
                "offline": 0,
            },
            "agents_with_errors": [],
            "slowest_agents": [],
        }

        agents_data = []

        for host in hosts:
            expected_interval = host.report_interval or DEFAULT_REPORT_INTERVAL
            seconds_since_last_report = (
                (now - host.last_seen).total_seconds() if host.last_seen else float('inf')
            )

            health_status = host.agent_health or "unknown"
            agent_info = {
                "host_id": host.id,
                "hostname": host.hostname,
                "agent_version": host.agent_version,
                "agent_health": health_status,
                "is_online": host.is_online,
                "last_seen": host.last_seen.isoformat() if host.last_seen else None,
                "seconds_since_last_report": int(seconds_since_last_report),
                "report_interval": expected_interval,
                "reports_count": host.reports_count or 0,
                "errors_count": host.errors_count or 0,
                "consecutive_failures": host.consecutive_failures or 0,
                "last_report_duration_ms": host.last_report_duration,
                "avg_report_duration_ms": host.avg_report_duration,
                "uptime_seconds": host.uptime_seconds,
                "last_error": host.last_error,
                "last_error_at": host.last_error_at.isoformat() if host.last_error_at else None,
            }

            agents_data.append(agent_info)

            # Comptabiliser par statut
            summary["by_status"][health_status].append(agent_info)
            summary["stats"][health_status] += 1

            if host.is_online:
                summary["stats"]["online"] += 1
            else:
                summary["stats"]["offline"] += 1

            # Agents avec erreurs récentes
            if host.last_error and host.last_error_at:
                if (now - host.last_error_at).total_seconds() < 3600:  # Dernière heure
                    summary["agents_with_errors"].append(agent_info)

        # Trier les agents les plus lents par durée moyenne de rapport
        summary["slowest_agents"] = sorted(
            [a for a in agents_data if a["avg_report_duration_ms"]],
            key=lambda x: x["avg_report_duration_ms"],
            reverse=True
        )[:5]

        return summary

    async def get_agent_health(self, host_id: str) -> Optional[Dict[str, Any]]:
        """
        Retourne les détails de santé d'un agent spécifique.

        Args:
            host_id: ID de l'hôte

        Returns:
            Dict avec les informations de santé ou None
        """
        result = await self.db.execute(
            select(Host).where(Host.id == host_id)
        )
        host = result.scalar_one_or_none()

        if not host:
            return None

        now = datetime.utcnow()
        expected_interval = host.report_interval or DEFAULT_REPORT_INTERVAL
        seconds_since_last_report = (
            (now - host.last_seen).total_seconds() if host.last_seen else None
        )

        return {
            "host_id": host.id,
            "hostname": host.hostname,
            "agent_version": host.agent_version,
            "agent_health": host.agent_health or "unknown",
            "is_online": host.is_online,
            "first_seen": host.first_seen.isoformat() if host.first_seen else None,
            "last_seen": host.last_seen.isoformat() if host.last_seen else None,
            "seconds_since_last_report": int(seconds_since_last_report) if seconds_since_last_report else None,
            "report_interval": expected_interval,
            "last_report_duration_ms": host.last_report_duration,
            "avg_report_duration_ms": host.avg_report_duration,
            "reports_count": host.reports_count or 0,
            "errors_count": host.errors_count or 0,
            "consecutive_failures": host.consecutive_failures or 0,
            "uptime_seconds": host.uptime_seconds,
            "last_error": host.last_error,
            "last_error_at": host.last_error_at.isoformat() if host.last_error_at else None,
            "docker_version": host.docker_version,
            "os_info": host.os_info,
            "tailscale_ip": host.tailscale_ip,
            "tailscale_hostname": host.tailscale_hostname,
        }

    async def reset_agent_stats(self, host_id: str) -> bool:
        """
        Réinitialise les statistiques d'un agent.

        Args:
            host_id: ID de l'hôte

        Returns:
            True si réussi, False si non trouvé
        """
        result = await self.db.execute(
            select(Host).where(Host.id == host_id)
        )
        host = result.scalar_one_or_none()

        if not host:
            return False

        host.reports_count = 0
        host.errors_count = 0
        host.consecutive_failures = 0
        host.avg_report_duration = None
        host.last_error = None
        host.last_error_at = None
        host.agent_health = "unknown"

        await self.db.commit()
        return True
