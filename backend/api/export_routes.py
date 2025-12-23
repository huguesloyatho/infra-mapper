"""Export routes for Infra-Mapper - CSV, JSON, PDF exports."""

import csv
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from services.graph_service import GraphService
from db.models import Host, Container, Connection

router = APIRouter(prefix="/api/v1/export", tags=["export"])


@router.get("/inventory/json")
async def export_inventory_json(
    db: AsyncSession = Depends(get_db),
    include_offline: bool = Query(True, description="Include offline containers"),
    host_filter: Optional[str] = Query(None, description="Filter by hostname"),
):
    """Export full inventory as JSON."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # Build query for hosts with their containers
    query = select(Host).options(selectinload(Host.containers))

    if host_filter:
        query = query.where(Host.hostname.ilike(f"%{host_filter}%"))

    result = await db.execute(query)
    hosts = result.scalars().all()

    inventory = {
        "exported_at": datetime.utcnow().isoformat(),
        "total_hosts": len(hosts),
        "total_containers": 0,
        "hosts": []
    }

    for host in hosts:
        containers = host.containers
        if not include_offline:
            containers = [c for c in containers if c.status.value == "running"]

        inventory["total_containers"] += len(containers)

        host_data = {
            "id": str(host.id),
            "hostname": host.hostname,
            "ip_addresses": host.ip_addresses,
            "tailscale_ip": host.tailscale_ip,
            "os_info": host.os_info,
            "docker_version": host.docker_version,
            "last_seen": host.last_seen.isoformat() if host.last_seen else None,
            "is_online": host.is_online,
            "agent_version": host.agent_version,
            "agent_health": host.agent_health,
            "containers": []
        }

        for container in containers:
            status_val = container.status.value if hasattr(container.status, 'value') else str(container.status)
            host_data["containers"].append({
                "id": str(container.id),
                "container_id": container.container_id,
                "name": container.name,
                "image": container.image,
                "status": status_val,
                "ports": container.ports,
                "networks": container.networks,
                "labels": container.labels,
                "compose_project": container.compose_project,
                "compose_service": container.compose_service,
                "created_at": container.created_at.isoformat() if container.created_at else None,
            })

        inventory["hosts"].append(host_data)

    return inventory


@router.get("/inventory/csv")
async def export_inventory_csv(
    db: AsyncSession = Depends(get_db),
    include_offline: bool = Query(True, description="Include offline containers"),
    host_filter: Optional[str] = Query(None, description="Filter by hostname"),
):
    """Export containers inventory as CSV."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # Build query
    query = select(Host).options(selectinload(Host.containers))

    if host_filter:
        query = query.where(Host.hostname.ilike(f"%{host_filter}%"))

    result = await db.execute(query)
    hosts = result.scalars().all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Host", "Host IPs", "Tailscale IP", "Container Name", "Container ID",
        "Image", "Status", "Project", "Ports", "Networks", "Created"
    ])

    # Data rows
    for host in hosts:
        containers = host.containers
        if not include_offline:
            containers = [c for c in containers if c.status.value == "running"]

        for container in containers:
            ports_str = ", ".join([
                f"{p.get('PrivatePort', '')}:{p.get('PublicPort', '')}/{p.get('Type', '')}"
                for p in (container.ports or [])
            ])
            networks_str = ", ".join(container.networks or [])
            host_ips = ", ".join(host.ip_addresses or [])
            status_val = container.status.value if hasattr(container.status, 'value') else str(container.status)

            writer.writerow([
                host.hostname,
                host_ips,
                host.tailscale_ip or "",
                container.name,
                container.container_id[:12] if container.container_id else "",
                container.image,
                status_val,
                container.compose_project or "",
                ports_str,
                networks_str,
                container.created_at.strftime("%Y-%m-%d %H:%M") if container.created_at else "",
            ])

    output.seek(0)
    filename = f"infra-mapper-inventory-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/connections/json")
async def export_connections_json(
    db: AsyncSession = Depends(get_db),
):
    """Export all network connections as JSON."""
    from sqlalchemy import select

    result = await db.execute(select(Connection))
    connections = result.scalars().all()

    export_data = {
        "exported_at": datetime.utcnow().isoformat(),
        "total_connections": len(connections),
        "connections": []
    }

    for conn in connections:
        export_data["connections"].append({
            "id": str(conn.id),
            "source_host_id": conn.source_host_id,
            "source_container_id": conn.source_container_id,
            "source_ip": conn.source_ip,
            "source_port": conn.source_port,
            "target_host_id": conn.target_host_id,
            "target_container_id": conn.target_container_id,
            "target_ip": conn.target_ip,
            "target_port": conn.target_port,
            "protocol": conn.protocol,
            "connection_type": conn.connection_type,
            "source_method": conn.source_method,
            "first_seen": conn.first_seen.isoformat() if conn.first_seen else None,
            "last_seen": conn.last_seen.isoformat() if conn.last_seen else None,
        })

    return export_data


@router.get("/connections/csv")
async def export_connections_csv(
    db: AsyncSession = Depends(get_db),
):
    """Export all network connections as CSV."""
    from sqlalchemy import select

    result = await db.execute(select(Connection))
    connections = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Source Host", "Source Container", "Source IP", "Source Port",
        "Target Host", "Target Container", "Target IP", "Target Port",
        "Protocol", "Connection Type", "Detection Method", "First Seen", "Last Seen"
    ])

    for conn in connections:
        writer.writerow([
            conn.source_host_id or "",
            conn.source_container_id or "",
            conn.source_ip or "",
            conn.source_port or "",
            conn.target_host_id or "",
            conn.target_container_id or "",
            conn.target_ip or "",
            conn.target_port or "",
            conn.protocol or "",
            conn.connection_type or "",
            conn.source_method or "",
            conn.first_seen.strftime("%Y-%m-%d %H:%M") if conn.first_seen else "",
            conn.last_seen.strftime("%Y-%m-%d %H:%M") if conn.last_seen else "",
        ])

    output.seek(0)
    filename = f"infra-mapper-connections-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/graph/json")
async def export_graph_json(
    db: AsyncSession = Depends(get_db),
    include_offline: bool = Query(True),
):
    """Export graph data as JSON (nodes and edges)."""
    graph_service = GraphService(db)
    graph = await graph_service.generate_graph(include_offline=include_offline)

    return {
        "exported_at": datetime.utcnow().isoformat(),
        "nodes": [n.model_dump() for n in graph.nodes],
        "edges": [e.model_dump() for e in graph.edges],
        "stats": {
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
        }
    }


@router.get("/report/summary")
async def export_summary_report(
    db: AsyncSession = Depends(get_db),
):
    """Generate a summary report of the infrastructure."""
    from sqlalchemy import select, func
    from db.models import ContainerStatusEnum

    # Count hosts
    host_result = await db.execute(select(func.count(Host.id)))
    total_hosts = host_result.scalar()

    host_online_result = await db.execute(select(func.count(Host.id)).where(Host.is_online == True))
    online_hosts = host_online_result.scalar()

    # Count containers
    container_result = await db.execute(select(func.count(Container.id)))
    total_containers = container_result.scalar()

    running_result = await db.execute(
        select(func.count(Container.id)).where(Container.status == ContainerStatusEnum.RUNNING)
    )
    running_containers = running_result.scalar()

    # Count connections
    conn_result = await db.execute(select(func.count(Connection.id)))
    total_connections = conn_result.scalar()

    # Connection types breakdown
    conn_types = await db.execute(
        select(Connection.connection_type, func.count(Connection.id))
        .group_by(Connection.connection_type)
    )
    connection_breakdown = {row[0] or "unknown": row[1] for row in conn_types.fetchall()}

    # Get containers by project
    projects = await db.execute(
        select(Container.compose_project, func.count(Container.id))
        .where(Container.compose_project.isnot(None))
        .group_by(Container.compose_project)
    )
    projects_breakdown = {row[0]: row[1] for row in projects.fetchall()}

    # Get hosts with their container counts
    hosts_result = await db.execute(
        select(Host.hostname, func.count(Container.id))
        .outerjoin(Container, Container.host_id == Host.id)
        .group_by(Host.id, Host.hostname)
    )
    hosts_breakdown = {row[0]: row[1] for row in hosts_result.fetchall()}

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "hosts": {
                "total": total_hosts,
                "online": online_hosts,
                "offline": total_hosts - online_hosts,
            },
            "containers": {
                "total": total_containers,
                "running": running_containers,
                "stopped": total_containers - running_containers,
            },
            "connections": {
                "total": total_connections,
                "by_type": connection_breakdown,
            },
        },
        "breakdown": {
            "containers_by_host": hosts_breakdown,
            "containers_by_project": projects_breakdown,
        }
    }
