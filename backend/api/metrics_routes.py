"""Routes API pour les métriques time-series."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from db import get_db
from services.metrics_service import MetricsService
from middleware import metrics_collector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


# =============================================================================
# Schemas
# =============================================================================

class MetricsQuery(BaseModel):
    """Paramètres de requête pour les métriques."""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    interval: int = Field(default=5, ge=1, le=60, description="Intervalle en minutes")


class HostMetricsResponse(BaseModel):
    """Réponse des métriques d'un host."""
    host_id: str
    hostname: Optional[str] = None
    period: str
    metrics: List[dict]


class ContainerMetricsResponse(BaseModel):
    """Réponse des métriques d'un container."""
    container_id: str
    container_name: Optional[str] = None
    period: str
    metrics: List[dict]


class HostSummaryResponse(BaseModel):
    """Résumé des métriques d'un host."""
    host_id: str
    period_hours: int
    sample_count: int
    cpu: dict
    memory: dict
    disk: dict


class AllHostsMetricsResponse(BaseModel):
    """Métriques actuelles de tous les hosts."""
    hosts: List[dict]
    timestamp: datetime


# =============================================================================
# Host Metrics Endpoints
# =============================================================================

@router.get("/hosts", response_model=AllHostsMetricsResponse)
async def get_all_hosts_metrics(db: AsyncSession = Depends(get_db)):
    """
    Récupère les métriques actuelles de tous les hosts.

    Idéal pour un dashboard de vue d'ensemble.
    """
    service = MetricsService(db)
    hosts = await service.get_all_hosts_current_metrics()

    return AllHostsMetricsResponse(
        hosts=hosts,
        timestamp=datetime.utcnow()
    )


@router.get("/hosts/{host_id}", response_model=HostMetricsResponse)
async def get_host_metrics(
    host_id: str,
    start: Optional[datetime] = Query(None, description="Début de la période (ISO 8601)"),
    end: Optional[datetime] = Query(None, description="Fin de la période (ISO 8601)"),
    hours: int = Query(1, ge=1, le=168, description="Nombre d'heures à récupérer"),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère les métriques time-series d'un host.

    Args:
        host_id: ID du host
        start: Début de la période (optionnel)
        end: Fin de la période (optionnel)
        hours: Si start/end non fournis, récupère les N dernières heures
    """
    service = MetricsService(db)

    if not end:
        end = datetime.utcnow()
    if not start:
        start = end - timedelta(hours=hours)

    metrics = await service.get_host_metrics(host_id, start, end)

    return HostMetricsResponse(
        host_id=host_id,
        period=f"{start.isoformat()} - {end.isoformat()}",
        metrics=metrics,
    )


@router.get("/hosts/{host_id}/latest")
async def get_host_latest_metrics(
    host_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Récupère les dernières métriques d'un host."""
    service = MetricsService(db)
    metrics = await service.get_host_latest_metrics(host_id)

    if not metrics:
        raise HTTPException(status_code=404, detail="Métriques non trouvées")

    return metrics


@router.get("/hosts/{host_id}/summary", response_model=HostSummaryResponse)
async def get_host_summary(
    host_id: str,
    hours: int = Query(24, ge=1, le=168, description="Période en heures"),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère un résumé des métriques d'un host.

    Retourne les moyennes et maximums sur la période.
    """
    service = MetricsService(db)
    summary = await service.get_host_summary(host_id, hours)

    return HostSummaryResponse(
        host_id=host_id,
        **summary
    )


# =============================================================================
# Container Metrics Endpoints
# =============================================================================

@router.get("/containers/{container_id}", response_model=ContainerMetricsResponse)
async def get_container_metrics(
    container_id: str,
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    hours: int = Query(1, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère les métriques time-series d'un container.

    Args:
        container_id: ID du container (format: host_id:short_id)
    """
    service = MetricsService(db)

    if not end:
        end = datetime.utcnow()
    if not start:
        start = end - timedelta(hours=hours)

    metrics = await service.get_container_metrics(container_id, start, end)

    return ContainerMetricsResponse(
        container_id=container_id,
        period=f"{start.isoformat()} - {end.isoformat()}",
        metrics=metrics,
    )


@router.get("/containers/{container_id}/latest")
async def get_container_latest_metrics(
    container_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Récupère les dernières métriques d'un container."""
    service = MetricsService(db)
    metrics = await service.get_container_latest_metrics(container_id)

    if not metrics:
        raise HTTPException(status_code=404, detail="Métriques non trouvées")

    return metrics


# =============================================================================
# Export & Cleanup
# =============================================================================

@router.get("/prometheus", response_class=Response)
async def export_prometheus_metrics(db: AsyncSession = Depends(get_db)):
    """
    Exporte les métriques au format Prometheus.

    Utilisable comme endpoint pour Prometheus scraping.
    Inclut les métriques d'infrastructure ET les métriques internes du backend.
    """
    service = MetricsService(db)

    # Métriques d'infrastructure (hosts, containers)
    infra_content = await service.export_prometheus_metrics()

    # Métriques internes du backend (latence, requêtes, erreurs)
    internal_content = metrics_collector.export_prometheus()

    # Combiner les deux
    content = f"{infra_content}\n\n# Backend internal metrics\n{internal_content}"

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
    )


@router.get("/internal")
async def get_internal_metrics():
    """
    Récupère les métriques internes du backend en JSON.

    Inclut:
    - Uptime
    - Nombre total de requêtes et erreurs
    - Taux de requêtes par seconde
    - Top endpoints par volume
    - Endpoints les plus lents
    """
    return metrics_collector.get_stats()


@router.post("/cleanup")
async def cleanup_metrics(
    retention_days: int = Query(7, ge=1, le=90, description="Jours de rétention"),
    db: AsyncSession = Depends(get_db),
):
    """
    Supprime les métriques plus anciennes que retention_days.

    Par défaut, garde 7 jours de métriques.
    """
    service = MetricsService(db)
    result = await service.cleanup_old_metrics(retention_days)

    return result
