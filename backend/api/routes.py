"""Routes de l'API."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db import get_db
from models import (
    AgentReport,
    GraphData,
    DashboardCreate,
    DashboardUpdate,
    DashboardResponse,
    SavePositionsRequest,
    NodePosition,
    # VM Management
    VmCreate,
    VmUpdate,
    VmResponse,
    # Agent Actions
    AgentDeployRequest,
    AgentActionRequest,
    AgentLogsResponse,
    SshTestRequest,
    SshTestResponse,
    # Container Logs
    ContainerLogEntry,
    ContainerLogsResponse,
)
from services import ReportService, GraphService
from services.dashboard_service import DashboardService
from services.websocket_manager import ws_manager
from services.vm_service import VmService
from services.ssh_service import SshService
from services.agent_deployment_service import AgentDeploymentService
from services.logs_service import LogsService
from services.ssh_key_service import SshKeyService

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def verify_api_key(authorization: str = Header(...)) -> bool:
    """Vérifie la clé API."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Format d'autorisation invalide")

    token = authorization.replace("Bearer ", "")
    if token != settings.api_key:
        raise HTTPException(status_code=401, detail="Clé API invalide")

    return True


# === Routes Agent ===

@router.post("/api/v1/report")
async def receive_report(
    report: AgentReport,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_api_key),
):
    """Reçoit un rapport d'un agent."""
    try:
        service = ReportService(db)
        stats = await service.process_report(report)

        # Mettre à jour la santé de l'agent
        try:
            from services.agent_health_service import AgentHealthService
            health_service = AgentHealthService(db)
            agent_meta = report.agent
            await health_service.update_agent_health(
                host_id=report.host.agent_id,
                agent_version=agent_meta.version if agent_meta else None,
                report_interval=agent_meta.report_interval if agent_meta else None,
                report_duration_ms=agent_meta.report_duration_ms if agent_meta else None,
                uptime_seconds=agent_meta.uptime_seconds if agent_meta else None,
                error=agent_meta.error if agent_meta else None,
                command_port=agent_meta.command_port if agent_meta else None,
            )
        except Exception as health_error:
            logger.warning(f"Erreur mise à jour santé agent: {health_error}")

        # Évaluer les règles d'alerte après chaque rapport
        try:
            from services.alert_service import AlertService
            alert_service = AlertService(db)
            new_alerts = await alert_service.evaluate_all_rules()
            stats["alerts_triggered"] = len(new_alerts)
        except Exception as alert_error:
            logger.warning(f"Erreur évaluation alertes: {alert_error}")
            stats["alerts_triggered"] = 0

        # Notifier les clients WebSocket
        await ws_manager.notify_host_update(
            report.host.agent_id,
            report.host.hostname
        )
        await ws_manager.notify_graph_refresh()

        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.error(f"Erreur traitement rapport: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === Routes Graphe ===

@router.get("/api/v1/graph", response_model=GraphData)
async def get_graph(
    include_offline: bool = False,
    host_filter: Optional[str] = None,
    project_filter: Optional[str] = None,
    organization_id: Optional[str] = None,
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Retourne les données du graphe d'infrastructure."""
    try:
        service = GraphService(db)
        graph = await service.generate_graph(
            include_offline=include_offline,
            host_filter=host_filter,
            project_filter=project_filter,
            organization_id=organization_id,
            team_id=team_id,
        )
        return graph
    except Exception as e:
        logger.error(f"Erreur génération graphe: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/hosts")
async def get_hosts_summary(
    organization_id: Optional[str] = None,
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Retourne un résumé de tous les hôtes."""
    try:
        service = GraphService(db)
        return await service.get_host_summary(
            organization_id=organization_id,
            team_id=team_id,
        )
    except Exception as e:
        logger.error(f"Erreur récupération hôtes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === WebSocket ===

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Endpoint WebSocket pour les mises à jour temps réel."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Garder la connexion ouverte
            data = await websocket.receive_text()
            # On pourrait traiter des commandes ici si nécessaire
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"Erreur WebSocket: {e}")
        ws_manager.disconnect(websocket)


# === Santé ===

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Vérification de santé détaillée.

    Retourne:
    - status: "healthy" ou "degraded"
    - database: état de la connexion DB
    - uptime: temps de fonctionnement
    - version: version de l'application
    """
    from middleware import metrics_collector
    from sqlalchemy import text

    health_status = "healthy"
    db_status = "connected"

    # Vérifier la connexion DB
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"
        health_status = "degraded"

    # Récupérer les stats internes
    stats = metrics_collector.get_stats()

    return {
        "status": health_status,
        "database": db_status,
        "uptime_seconds": round(stats.get("uptime_seconds", 0), 2),
        "version": "1.0.0",
        "requests": {
            "total": stats.get("total_requests", 0),
            "errors": stats.get("total_errors", 0),
            "per_second": stats.get("requests_per_second", 0),
            "error_rate_percent": stats.get("error_rate_percent", 0),
        }
    }


@router.get("/api/v1/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Retourne des statistiques générales."""
    from sqlalchemy import select, func
    from db.models import Host, Container, Connection

    try:
        # Compter les hôtes
        hosts_result = await db.execute(select(func.count(Host.id)))
        hosts_count = hosts_result.scalar()

        # Compter les conteneurs
        containers_result = await db.execute(select(func.count(Container.id)))
        containers_count = containers_result.scalar()

        # Compter les connexions
        connections_result = await db.execute(select(func.count(Connection.id)))
        connections_count = connections_result.scalar()

        return {
            "hosts": hosts_count,
            "containers": containers_count,
            "connections": connections_count,
            "websocket_clients": len(ws_manager.active_connections),
        }
    except Exception as e:
        logger.error(f"Erreur stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === Routes Dashboards ===

@router.get("/api/v1/dashboards", response_model=list[DashboardResponse])
async def list_dashboards(db: AsyncSession = Depends(get_db)):
    """Liste tous les dashboards personnalisés."""
    try:
        service = DashboardService(db)
        return await service.list_dashboards()
    except Exception as e:
        logger.error(f"Erreur liste dashboards: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/dashboards", response_model=DashboardResponse)
async def create_dashboard(
    data: DashboardCreate,
    db: AsyncSession = Depends(get_db),
):
    """Crée un nouveau dashboard."""
    try:
        service = DashboardService(db)
        return await service.create_dashboard(data)
    except Exception as e:
        logger.error(f"Erreur création dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Récupère un dashboard par son ID."""
    try:
        service = DashboardService(db)
        dashboards = await service.list_dashboards()
        for d in dashboards:
            if d.id == dashboard_id:
                return d
        raise HTTPException(status_code=404, detail="Dashboard non trouvé")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/v1/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: str,
    data: DashboardUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Met à jour un dashboard."""
    try:
        service = DashboardService(db)
        result = await service.update_dashboard(dashboard_id, data)
        if not result:
            raise HTTPException(status_code=404, detail="Dashboard non trouvé")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur mise à jour dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/dashboards/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Supprime un dashboard."""
    try:
        service = DashboardService(db)
        success = await service.delete_dashboard(dashboard_id)
        if not success:
            raise HTTPException(status_code=404, detail="Dashboard non trouvé")
        return {"status": "deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/dashboards/{dashboard_id}/graph")
async def get_dashboard_graph(
    dashboard_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Récupère le graphe avec les positions sauvegardées."""
    try:
        service = DashboardService(db)
        graph, positions = await service.get_graph_with_positions(dashboard_id)

        return {
            "graph": graph.model_dump(),
            "positions": {k: v.model_dump() for k, v in positions.items()},
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur récupération graphe dashboard: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/dashboards/{dashboard_id}/positions")
async def save_positions(
    dashboard_id: str,
    data: SavePositionsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Sauvegarde les positions des nœuds."""
    try:
        service = DashboardService(db)

        # Vérifier que le dashboard existe
        dashboard = await service.get_dashboard(dashboard_id)
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard non trouvé")

        # Récupérer les IDs des nœuds actuels depuis le graphe
        graph_service = GraphService(db)
        graph = await graph_service.generate_graph(
            include_offline=dashboard.include_offline,
            host_filter=dashboard.host_filter,
            project_filter=dashboard.project_filter,
        )
        current_node_ids = {n.id for n in graph.nodes}

        count = await service.save_positions(dashboard_id, data.positions, current_node_ids)
        return {"status": "saved", "count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur sauvegarde positions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/dashboards/purge")
async def purge_old_nodes(db: AsyncSession = Depends(get_db)):
    """Purge les nœuds disparus depuis plus de 7 jours."""
    try:
        service = DashboardService(db)
        count = await service.purge_old_nodes()
        return {"status": "purged", "count": count}
    except Exception as e:
        logger.error(f"Erreur purge: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === Routes VM Management ===

@router.get("/api/v1/vms", response_model=list[VmResponse])
async def list_vms(
    include_auto_discovered: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Liste toutes les VMs managées."""
    try:
        service = VmService(db)
        vms = await service.list_vms(include_auto_discovered)
        return [
            VmResponse(
                id=vm.id,
                name=vm.name,
                hostname=vm.hostname,
                ip_address=vm.ip_address,
                ssh_port=vm.ssh_port,
                ssh_user=vm.ssh_user,
                os_type=vm.os_type.value if vm.os_type else "unknown",
                status=vm.status.value if vm.status else "pending",
                host_id=vm.host_id,
                agent_version=vm.agent_version,
                agent_installed_at=vm.agent_installed_at,
                is_auto_discovered=vm.is_auto_discovered,
                tags=vm.tags or [],
                notes=vm.notes,
                created_at=vm.created_at,
                updated_at=vm.updated_at,
            )
            for vm in vms
        ]
    except Exception as e:
        logger.error(f"Erreur liste VMs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/vms", response_model=VmResponse)
async def create_vm(
    data: VmCreate,
    db: AsyncSession = Depends(get_db),
):
    """Crée une nouvelle VM."""
    try:
        service = VmService(db)
        vm = await service.create_vm(data)
        return VmResponse(
            id=vm.id,
            name=vm.name,
            hostname=vm.hostname,
            ip_address=vm.ip_address,
            ssh_port=vm.ssh_port,
            ssh_user=vm.ssh_user,
            os_type=vm.os_type.value if vm.os_type else "unknown",
            status=vm.status.value if vm.status else "pending",
            host_id=vm.host_id,
            agent_version=vm.agent_version,
            agent_installed_at=vm.agent_installed_at,
            is_auto_discovered=vm.is_auto_discovered,
            tags=vm.tags or [],
            notes=vm.notes,
            created_at=vm.created_at,
            updated_at=vm.updated_at,
        )
    except Exception as e:
        logger.error(f"Erreur création VM: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/vms/{vm_id}", response_model=VmResponse)
async def get_vm(
    vm_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Récupère une VM par son ID."""
    try:
        service = VmService(db)
        vm = await service.get_vm(vm_id)
        if not vm:
            raise HTTPException(status_code=404, detail="VM non trouvée")
        return VmResponse(
            id=vm.id,
            name=vm.name,
            hostname=vm.hostname,
            ip_address=vm.ip_address,
            ssh_port=vm.ssh_port,
            ssh_user=vm.ssh_user,
            os_type=vm.os_type.value if vm.os_type else "unknown",
            status=vm.status.value if vm.status else "pending",
            host_id=vm.host_id,
            agent_version=vm.agent_version,
            agent_installed_at=vm.agent_installed_at,
            is_auto_discovered=vm.is_auto_discovered,
            tags=vm.tags or [],
            notes=vm.notes,
            created_at=vm.created_at,
            updated_at=vm.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération VM: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/v1/vms/{vm_id}", response_model=VmResponse)
async def update_vm(
    vm_id: str,
    data: VmUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Met à jour une VM."""
    try:
        service = VmService(db)
        vm = await service.update_vm(vm_id, data)
        if not vm:
            raise HTTPException(status_code=404, detail="VM non trouvée")
        return VmResponse(
            id=vm.id,
            name=vm.name,
            hostname=vm.hostname,
            ip_address=vm.ip_address,
            ssh_port=vm.ssh_port,
            ssh_user=vm.ssh_user,
            os_type=vm.os_type.value if vm.os_type else "unknown",
            status=vm.status.value if vm.status else "pending",
            host_id=vm.host_id,
            agent_version=vm.agent_version,
            agent_installed_at=vm.agent_installed_at,
            is_auto_discovered=vm.is_auto_discovered,
            tags=vm.tags or [],
            notes=vm.notes,
            created_at=vm.created_at,
            updated_at=vm.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur mise à jour VM: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/vms/{vm_id}")
async def delete_vm(
    vm_id: str,
    delete_agent: bool = False,
    delete_host_data: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    Supprime une VM.

    Args:
        vm_id: ID de la VM à supprimer
        delete_agent: Si True, supprime aussi l'agent sur la VM distante
        delete_host_data: Si True, supprime aussi le Host et ses données (containers, connections)
    """
    from db.models import Host

    try:
        vm_service = VmService(db)
        vm = await vm_service.get_vm(vm_id)
        if not vm:
            raise HTTPException(status_code=404, detail="VM non trouvée")

        # 1. Supprimer l'agent distant si demandé
        if delete_agent and vm.host_id:
            try:
                ssh = SshService()
                agent_service = AgentDeploymentService(db, ssh)
                await agent_service.delete_agent(vm)
                logger.info(f"Agent supprimé sur {vm.name}")
            except Exception as e:
                logger.warning(f"Impossible de supprimer l'agent sur {vm.name}: {e}")
                # Continue même si la suppression de l'agent échoue

        # 2. Supprimer le Host et ses données associées (cascade)
        if delete_host_data and vm.host_id:
            host = await db.get(Host, vm.host_id)
            if host:
                await db.delete(host)
                await db.commit()
                logger.info(f"Host {vm.host_id} et données associées supprimés")

        # 3. Supprimer la VM
        success = await vm_service.delete_vm(vm_id)
        if not success:
            raise HTTPException(status_code=404, detail="VM non trouvée")

        return {"status": "deleted", "agent_deleted": delete_agent, "host_data_deleted": delete_host_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression VM: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === Routes Agent Actions ===

@router.post("/api/v1/agents/deploy")
async def deploy_agents(
    request: AgentDeployRequest,
    db: AsyncSession = Depends(get_db),
):
    """Déploie l'agent sur les VMs sélectionnées."""
    try:
        ssh = SshService()
        service = AgentDeploymentService(db, ssh)
        vm_service = VmService(db)

        results = []
        for vm_id in request.vm_ids:
            vm = await vm_service.get_vm(vm_id)
            if vm:
                result = await service.deploy_agent(vm)
                results.append(result)
            else:
                results.append({"status": "error", "vm_id": vm_id, "message": "VM non trouvée"})

        return results
    except Exception as e:
        logger.error(f"Erreur déploiement agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/agents/action")
async def agent_action(
    request: AgentActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exécute une action sur les agents des VMs sélectionnées."""
    try:
        ssh = SshService()
        service = AgentDeploymentService(db, ssh)
        vm_service = VmService(db)

        results = []
        for vm_id in request.vm_ids:
            vm = await vm_service.get_vm(vm_id)
            if not vm:
                results.append({"status": "error", "vm_id": vm_id, "message": "VM non trouvée"})
                continue

            if request.action == "start":
                result = await service.start_agent(vm)
            elif request.action == "stop":
                result = await service.stop_agent(vm)
            elif request.action == "restart":
                result = await service.restart_agent(vm)
            elif request.action == "update":
                result = await service.update_agent(vm)
            elif request.action == "delete":
                result = await service.delete_agent(vm)
            else:
                result = {"status": "error", "vm_id": vm_id, "message": f"Action inconnue: {request.action}"}

            results.append(result)

        return results
    except Exception as e:
        logger.error(f"Erreur action agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/agents/{vm_id}/logs", response_model=AgentLogsResponse)
async def get_agent_logs(
    vm_id: str,
    lines: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Récupère les logs de l'agent d'une VM."""
    try:
        vm_service = VmService(db)
        vm = await vm_service.get_vm(vm_id)
        if not vm:
            raise HTTPException(status_code=404, detail="VM non trouvée")

        ssh = SshService()
        service = AgentDeploymentService(db, ssh)
        logs = await service.get_agent_logs(vm, lines)

        return AgentLogsResponse(vm_id=vm_id, logs=logs)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération logs agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/ssh/test", response_model=SshTestResponse)
async def test_ssh_connection(request: SshTestRequest):
    """Teste la connexion SSH vers une VM."""
    try:
        ssh = SshService()
        success, message, os_detected = await ssh.test_connection(
            request.ip_address,
            request.ssh_user,
            request.ssh_port
        )
        return SshTestResponse(
            success=success,
            message=message,
            os_detected=os_detected
        )
    except Exception as e:
        logger.error(f"Erreur test SSH: {e}", exc_info=True)
        return SshTestResponse(
            success=False,
            message=str(e),
            os_detected=None
        )


# === Routes Containers ===

@router.get("/api/v1/containers")
async def list_containers(
    host_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Liste tous les containers avec filtre optionnel par host."""
    from db.models import Container, Host
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    try:
        query = select(Container).options(selectinload(Container.host))

        if host_id:
            query = query.where(Container.host_id == host_id)

        query = query.order_by(Container.name)
        result = await db.execute(query)
        containers = result.scalars().all()

        return [
            {
                "id": c.id,
                "container_id": c.container_id,
                "host_id": c.host_id,
                "host_name": c.host.hostname if c.host else None,
                "name": c.name,
                "image": c.image,
                "status": c.status.value if c.status else "unknown",
                "health": c.health.value if c.health else "none",
            }
            for c in containers
        ]
    except Exception as e:
        logger.error(f"Erreur listing containers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === Routes Container Logs ===

@router.get("/api/v1/containers/{container_id}/logs", response_model=ContainerLogsResponse)
async def get_container_logs(
    container_id: str,
    limit: int = 500,
    offset: int = 0,
    search: Optional[str] = None,
    stream: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Récupère les logs d'un container."""
    try:
        service = LogsService(db)
        logs, total = await service.get_container_logs(
            container_id,
            limit=limit,
            offset=offset,
            search=search,
            stream=stream
        )

        # Enrichir avec les infos du container
        container_info = await service.get_container_info(container_id)
        container_name = container_info.get("container_name", "") if container_info else ""
        host_name = container_info.get("host_name", "") if container_info else ""

        return ContainerLogsResponse(
            container_id=container_id,
            container_name=container_name,
            host_name=host_name,
            logs=[
                ContainerLogEntry(
                    timestamp=log.timestamp,
                    stream=log.stream,
                    message=log.message
                )
                for log in logs
            ],
            total=total
        )
    except Exception as e:
        logger.error(f"Erreur récupération logs container: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/hosts/{host_id}/logs")
async def get_host_logs(
    host_id: str,
    limit: int = 500,
    db: AsyncSession = Depends(get_db),
):
    """Récupère tous les logs d'un hôte."""
    try:
        service = LogsService(db)
        logs = await service.get_host_logs(host_id, limit)
        return [
            {
                "container_id": log.container_id,
                "timestamp": log.timestamp.isoformat(),
                "stream": log.stream,
                "message": log.message
            }
            for log in logs
        ]
    except Exception as e:
        logger.error(f"Erreur récupération logs hôte: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/logs/stats")
async def get_logs_stats(db: AsyncSession = Depends(get_db)):
    """Retourne des statistiques sur les logs."""
    try:
        service = LogsService(db)
        return await service.get_logs_stats()
    except Exception as e:
        logger.error(f"Erreur stats logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/logs/cleanup")
async def cleanup_logs(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """Nettoie les logs plus vieux que N jours."""
    try:
        service = LogsService(db)
        count = await service.cleanup_old_logs(days)
        return {"status": "cleaned", "count": count}
    except Exception as e:
        logger.error(f"Erreur nettoyage logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === Routes SSH Key Management ===

@router.get("/api/v1/ssh/key")
async def get_ssh_key_info():
    """Récupère les informations sur la clé SSH du backend."""
    try:
        service = SshKeyService()
        return service.get_key_info()
    except Exception as e:
        logger.error(f"Erreur récupération info clé SSH: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/ssh/key/generate")
async def generate_ssh_key(force: bool = False):
    """Génère une nouvelle paire de clés SSH."""
    try:
        service = SshKeyService()
        success, message = service.generate_key(force=force)
        if not success:
            raise HTTPException(status_code=400, detail=message)
        return {"status": "success", "message": message, "key_info": service.get_key_info()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur génération clé SSH: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel

class DeployKeyRequest(BaseModel):
    """Requête de déploiement de clé SSH."""
    host: str
    user: str
    port: int = 22
    password: str


@router.post("/api/v1/ssh/key/deploy")
async def deploy_ssh_key(request: DeployKeyRequest):
    """Déploie la clé SSH sur un hôte distant."""
    try:
        service = SshKeyService()
        success, message = await service.deploy_key_to_host(
            host=request.host,
            user=request.user,
            port=request.port,
            password=request.password,
        )
        if not success:
            raise HTTPException(status_code=400, detail=message)
        return {"status": "success", "message": message}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur déploiement clé SSH: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/vms/{vm_id}/deploy-key")
async def deploy_key_to_vm(
    vm_id: str,
    password: str,
    db: AsyncSession = Depends(get_db),
):
    """Déploie la clé SSH sur une VM spécifique."""
    try:
        vm_service = VmService(db)
        vm = await vm_service.get_vm(vm_id)
        if not vm:
            raise HTTPException(status_code=404, detail="VM non trouvée")

        ssh_key_service = SshKeyService()
        success, message = await ssh_key_service.deploy_key_to_host(
            host=vm.ip_address,
            user=vm.ssh_user,
            port=vm.ssh_port,
            password=password,
        )

        if not success:
            raise HTTPException(status_code=400, detail=message)

        return {"status": "success", "message": message, "vm_id": vm_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur déploiement clé sur VM {vm_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
