"""Routes API pour les actions sur containers via les agents."""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from db.models import Host, Container
from models.schemas import (
    ContainerActionRequest,
    ContainerActionResponse,
    ContainerExecRequest,
    ContainerExecResponse,
    ContainerStatsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/containers", tags=["container-actions"])

# Timeout pour les requêtes vers l'agent
AGENT_REQUEST_TIMEOUT = 60.0


async def get_agent_info(db: AsyncSession, container_id: str) -> tuple[str, str, str]:
    """
    Récupère l'URL de l'agent et l'ID Docker court pour un container donné.

    Returns:
        Tuple (agent_url, api_key, docker_container_id) ou lève HTTPException si non trouvé
    """
    # Trouver le container
    result = await db.execute(
        select(Container).where(Container.id == container_id)
    )
    container = result.scalar_one_or_none()

    if not container:
        raise HTTPException(status_code=404, detail=f"Container {container_id} not found")

    # Trouver l'hôte associé
    result = await db.execute(
        select(Host).where(Host.id == container.host_id)
    )
    host = result.scalar_one_or_none()

    if not host:
        raise HTTPException(status_code=404, detail=f"Host for container {container_id} not found")

    if not host.is_online:
        raise HTTPException(status_code=503, detail=f"Host {host.hostname} is offline")

    if not host.command_port:
        raise HTTPException(
            status_code=503,
            detail=f"Agent on {host.hostname} does not have command server enabled"
        )

    # Utiliser l'IP Tailscale si disponible, sinon la première IP
    agent_ip = host.tailscale_ip or (host.ip_addresses[0] if host.ip_addresses else None)
    if not agent_ip:
        raise HTTPException(
            status_code=503,
            detail=f"No IP address available for host {host.hostname}"
        )

    agent_url = f"http://{agent_ip}:{host.command_port}"

    # Récupérer l'API key depuis les settings (utiliser la même que celle configurée)
    from config import get_settings
    settings = get_settings()

    # Retourner l'ID Docker court (container_id) pour l'agent
    return agent_url, settings.api_key, container.container_id


async def send_agent_request(
    agent_url: str,
    api_key: str,
    endpoint: str,
    data: dict
) -> dict:
    """Envoie une requête à l'agent."""
    async with httpx.AsyncClient(timeout=AGENT_REQUEST_TIMEOUT) as client:
        try:
            response = await client.post(
                f"{agent_url}{endpoint}",
                json=data,
                headers={"Authorization": f"Bearer {api_key}"}
            )
            return response.json()
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Agent request timed out")
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Cannot reach agent: {str(e)}")


@router.post("/{container_id}/start", response_model=ContainerActionResponse)
async def start_container(
    container_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Démarre un container."""
    agent_url, api_key, docker_id = await get_agent_info(db, container_id)
    result = await send_agent_request(
        agent_url, api_key, "/containers/start",
        {"container_id": docker_id}
    )
    return ContainerActionResponse(**result)


@router.post("/{container_id}/stop", response_model=ContainerActionResponse)
async def stop_container(
    container_id: str,
    timeout: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Arrête un container."""
    agent_url, api_key, docker_id = await get_agent_info(db, container_id)
    result = await send_agent_request(
        agent_url, api_key, "/containers/stop",
        {"container_id": docker_id, "timeout": timeout}
    )
    return ContainerActionResponse(**result)


@router.post("/{container_id}/restart", response_model=ContainerActionResponse)
async def restart_container(
    container_id: str,
    timeout: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Redémarre un container."""
    agent_url, api_key, docker_id = await get_agent_info(db, container_id)
    result = await send_agent_request(
        agent_url, api_key, "/containers/restart",
        {"container_id": docker_id, "timeout": timeout}
    )
    return ContainerActionResponse(**result)


@router.post("/{container_id}/exec", response_model=ContainerExecResponse)
async def exec_in_container(
    container_id: str,
    request: ContainerExecRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Exécute une commande dans un container.

    ATTENTION: Cette fonctionnalité est puissante et peut être dangereuse.
    Limitez son accès aux administrateurs uniquement.
    """
    # Le container_id dans le body peut être soit l'ID complet soit l'ID Docker court
    agent_url, api_key, docker_id = await get_agent_info(db, container_id)
    result = await send_agent_request(
        agent_url, api_key, "/containers/exec",
        {
            "container_id": docker_id,
            "command": request.command,
            "timeout": request.timeout,
            "workdir": request.workdir
        }
    )
    return ContainerExecResponse(**result)


@router.get("/{container_id}/stats", response_model=ContainerStatsResponse)
async def get_container_stats(
    container_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Récupère les statistiques temps réel d'un container."""
    agent_url, api_key, docker_id = await get_agent_info(db, container_id)
    result = await send_agent_request(
        agent_url, api_key, "/containers/stats",
        {"container_id": docker_id}
    )
    return ContainerStatsResponse(**result)


@router.post("/{container_id}/logs")
async def get_container_logs_live(
    container_id: str,
    lines: int = 100,
    since_seconds: int = 300,
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère les logs récents d'un container directement depuis l'agent.

    Contrairement à /api/v1/logs qui utilise les logs stockés en BDD,
    cette route récupère les logs en temps réel depuis l'agent.
    """
    agent_url, api_key, docker_id = await get_agent_info(db, container_id)
    result = await send_agent_request(
        agent_url, api_key, "/containers/logs",
        {
            "container_id": docker_id,
            "lines": lines,
            "since_seconds": since_seconds
        }
    )
    return result
