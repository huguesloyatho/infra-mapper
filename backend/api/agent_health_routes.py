"""Routes API pour le monitoring de santé des agents."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services.agent_health_service import AgentHealthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agents/health", tags=["agent-health"])


# =============================================================================
# Schemas
# =============================================================================

class AgentHealthSummary(BaseModel):
    """Résumé de la santé des agents."""
    total: int
    stats: dict
    by_status: dict
    agents_with_errors: list
    slowest_agents: list


class AgentHealthDetail(BaseModel):
    """Détail de santé d'un agent."""
    host_id: str
    hostname: str
    agent_version: Optional[str]
    agent_health: str
    is_online: bool
    first_seen: Optional[str]
    last_seen: Optional[str]
    seconds_since_last_report: Optional[int]
    report_interval: int
    last_report_duration_ms: Optional[int]
    avg_report_duration_ms: Optional[int]
    reports_count: int
    errors_count: int
    consecutive_failures: int
    uptime_seconds: Optional[int]
    last_error: Optional[str]
    last_error_at: Optional[str]
    docker_version: Optional[str]
    os_info: Optional[str]
    tailscale_ip: Optional[str]
    tailscale_hostname: Optional[str]


class HealthCheckResponse(BaseModel):
    """Réponse du check périodique de santé."""
    total: int
    healthy: int
    degraded: int
    unhealthy: int
    unknown: int
    offline: int
    updated_hosts: list


# =============================================================================
# Routes
# =============================================================================

@router.get("/summary", response_model=AgentHealthSummary)
async def get_agents_health_summary(
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne un résumé de la santé de tous les agents.

    Inclut:
    - Statistiques globales (healthy, degraded, unhealthy, unknown)
    - Liste des agents par statut
    - Agents avec erreurs récentes (dernière heure)
    - Top 5 des agents les plus lents
    """
    try:
        service = AgentHealthService(db)
        summary = await service.get_agents_health_summary()
        return summary
    except Exception as e:
        logger.error(f"Erreur récupération résumé santé: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{host_id}", response_model=AgentHealthDetail)
async def get_agent_health(
    host_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne les détails de santé d'un agent spécifique.
    """
    try:
        service = AgentHealthService(db)
        health = await service.get_agent_health(host_id)
        if not health:
            raise HTTPException(status_code=404, detail="Host not found")
        return health
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération santé agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check", response_model=HealthCheckResponse)
async def check_all_agents_health(
    db: AsyncSession = Depends(get_db),
):
    """
    Exécute une vérification de santé de tous les agents.

    Cette route devrait être appelée périodiquement (via cron ou scheduler)
    pour détecter les agents qui ne répondent plus.

    Met à jour le statut des agents qui:
    - N'ont pas envoyé de rapport depuis trop longtemps (unhealthy)
    - Ont un délai anormal entre les rapports (degraded)
    """
    try:
        service = AgentHealthService(db)
        stats = await service.check_all_agents_health()
        return stats
    except Exception as e:
        logger.error(f"Erreur check santé agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{host_id}/reset")
async def reset_agent_stats(
    host_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Réinitialise les statistiques de santé d'un agent.

    Remet à zéro:
    - Compteurs de rapports et d'erreurs
    - Échecs consécutifs
    - Durée moyenne des rapports
    - Dernière erreur
    """
    try:
        service = AgentHealthService(db)
        success = await service.reset_agent_stats(host_id)
        if not success:
            raise HTTPException(status_code=404, detail="Host not found")
        return {"status": "reset", "host_id": host_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur reset stats agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_agents_health(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les agents avec leurs informations de santé.

    Args:
        status: Filtre par statut (healthy, degraded, unhealthy, unknown)
    """
    try:
        service = AgentHealthService(db)
        summary = await service.get_agents_health_summary()

        # Si un filtre de statut est spécifié
        if status:
            if status not in summary["by_status"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: healthy, degraded, unhealthy, unknown"
                )
            agents = summary["by_status"][status]
        else:
            # Combiner tous les agents
            agents = []
            for status_agents in summary["by_status"].values():
                agents.extend(status_agents)

        return {
            "agents": agents,
            "total": len(agents),
            "stats": summary["stats"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur liste agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
