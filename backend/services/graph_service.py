"""Service de génération du graphe d'infrastructure."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Host, Container, Connection, ContainerStatusEnum
from db.auth_models import OrganizationHost, TeamHost
from models.schemas import GraphData, GraphNode, GraphEdge

logger = logging.getLogger(__name__)


class GraphService:
    """Service de génération du graphe d'infrastructure."""

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db

    async def generate_graph(
        self,
        include_offline: bool = False,
        host_filter: Optional[str] = None,
        project_filter: Optional[str] = None,
        organization_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> GraphData:
        """
        Génère les données du graphe pour la visualisation.

        Args:
            include_offline: Inclure les hôtes/conteneurs offline
            host_filter: Filtrer par hostname (pattern)
            project_filter: Filtrer par projet compose
            organization_id: Filtrer par organisation (multi-tenancy)
            team_id: Filtrer par équipe (multi-tenancy)
        """
        nodes = []
        edges = []
        seen_edges = set()  # Pour éviter les doublons

        # Récupérer les hôtes (avec filtrage organisation/équipe si spécifié)
        hosts = await self._get_hosts(
            include_offline, host_filter, organization_id, team_id
        )

        # Mapping pour résoudre les connexions
        container_by_host_ip = {}  # (host_id, IP conteneur) -> conteneur (évite collisions IP Docker)
        container_by_id = {}  # Clé: host_id:container_id
        host_by_ip = {}  # Toutes les IPs d'un hôte (LAN + Tailscale) -> host
        containers_by_host = {}  # host_id -> [containers]

        # Construire le mapping IP hôte -> host (pour résoudre les connexions cross-host)
        for host in hosts:
            # Ajouter toutes les IPs de l'hôte
            if host.ip_addresses:
                for ip in host.ip_addresses:
                    host_by_ip[ip] = host
            if host.tailscale_ip:
                host_by_ip[host.tailscale_ip] = host

        for host in hosts:
            # Récupérer les conteneurs de cet hôte
            containers = await self._get_containers(
                host.id,
                include_offline,
                project_filter
            )

            logger.debug(f"Host {host.hostname}: {len(containers)} conteneurs")

            # Stocker les conteneurs par hôte pour la résolution cross-host
            containers_by_host[host.id] = containers

            # On n'ajoute plus de nœud hôte - les conteneurs sont indépendants
            # et liés uniquement par leurs connexions réseau

            for container in containers:
                # Mapper les IPs avec host_id pour éviter collisions Docker
                # (172.19.0.2 peut exister sur plusieurs hôtes)
                if isinstance(container.ip_addresses, dict):
                    for ip in container.ip_addresses.values():
                        if ip:
                            container_by_host_ip[(host.id, ip)] = container

                # container.id est déjà au format "host_id:container_id"
                container_by_id[container.id] = container

                # Construire le label multi-ligne: nom, VM, ports exposés
                label_parts = [container.name]
                label_parts.append(f"VM: {host.hostname}")

                # Extraire les ports exposés sur 0.0.0.0 (IPv4)
                exposed_ports = []
                if container.ports:
                    for port in container.ports:
                        if isinstance(port, dict) and port.get("host_ip") == "0.0.0.0" and port.get("host_port"):
                            exposed_ports.append(str(port["host_port"]))

                if exposed_ports:
                    label_parts.append(f"Ports: {', '.join(exposed_ports)}")

                container_label = "\n".join(label_parts)

                # Ajouter le nœud conteneur (indépendant, pas de parent)
                container_node = GraphNode(
                    id=f"container:{container.id}",
                    label=container_label,
                    type="container",
                    data={
                        "container_id": container.container_id,
                        "image": container.image,
                        "status": container.status.value if container.status else "unknown",
                        "health": container.health.value if container.health else "none",
                        "ports": container.ports,
                        "compose_project": container.compose_project,
                        "compose_service": container.compose_service,
                        "networks": container.networks,
                        "host_id": host.id,
                        "hostname": host.hostname,
                    }
                )
                nodes.append(container_node)

                # Ajouter les dépendances déclarées (depuis docker-compose)
                if container.declared_dependencies:
                    for dep_service in container.declared_dependencies:
                        # Trouver le conteneur de dépendance dans le même projet
                        dep_container = await self._find_container_by_service(
                            host.id,
                            container.compose_project,
                            dep_service
                        )
                        if dep_container:
                            edge_id = f"dep:{container.id}:{dep_container.id}"
                            if edge_id not in seen_edges:
                                seen_edges.add(edge_id)
                                edges.append(GraphEdge(
                                    id=edge_id,
                                    source=f"container:{container.id}",
                                    target=f"container:{dep_container.id}",
                                    label="depends_on",
                                    type="dependency",
                                    data={"declared": True}
                                ))

        # Créer des liens implicites entre conteneurs du même projet compose SUR LE MÊME HÔTE
        # Tous les conteneurs d'un même projet/hôte peuvent communiquer entre eux
        project_containers: dict[tuple[str, str], list[str]] = {}  # (host_id, project) -> [container_ids]

        for node in nodes:
            if node.type == "container":
                project = node.data.get("compose_project", "")
                host_id = node.data.get("host_id", "")
                if project and host_id:
                    key = (host_id, project)
                    if key not in project_containers:
                        project_containers[key] = []
                    project_containers[key].append(node.id)

        # Pour chaque projet/hôte, lier les conteneurs entre eux
        for (host_id, project), container_ids in project_containers.items():
            if len(container_ids) > 1:
                # Créer une topologie en étoile : le premier conteneur comme hub
                # Cela évite trop de liens tout en montrant la connexité
                hub = container_ids[0]
                for other in container_ids[1:]:
                    edge_id = f"project:{hub}:{other}"
                    reverse_edge_id = f"project:{other}:{hub}"
                    if edge_id not in seen_edges and reverse_edge_id not in seen_edges:
                        seen_edges.add(edge_id)
                        edges.append(GraphEdge(
                            id=edge_id,
                            source=hub,
                            target=other,
                            type="dependency",
                            label=project,
                            data={"project": project, "implicit": True}
                        ))

        # Ajouter les connexions réseau détectées
        connections = await self._get_connections([h.id for h in hosts])

        external_count = 0
        max_external = 20  # Limiter les nœuds externes

        # Dictionnaire pour stocker les edges avec leurs métadonnées
        # Clé: (source_id, target_id) -> {data avec source_methods}
        edge_data = {}

        for conn in connections:
            source_id = None
            target_id = None

            # Trouver la source - uniquement si c'est un conteneur
            if conn.source_container_id:
                full_source_id = f"{conn.source_host_id}:{conn.source_container_id}"
                if full_source_id in container_by_id:
                    source_id = f"container:{full_source_id}"
            # Si pas de conteneur source, on ignore cette connexion

            if not source_id:
                continue

            # Trouver la cible - d'abord par IP conteneur sur le même hôte (évite collisions Docker)
            source_host_id = conn.source_host_id
            target_container = container_by_host_ip.get((source_host_id, conn.target_ip))

            if not target_container:
                # L'IP cible est peut-être une IP d'hôte (LAN ou Tailscale)
                # Dans ce cas, résoudre vers le conteneur qui expose le port cible
                target_host = host_by_ip.get(conn.target_ip)
                if target_host and target_host.id in containers_by_host:
                    # Chercher le conteneur qui expose ce port sur cet hôte
                    for container in containers_by_host[target_host.id]:
                        if container.ports:
                            for port in container.ports:
                                if isinstance(port, dict):
                                    host_port = port.get("host_port")
                                    if host_port and int(host_port) == conn.target_port:
                                        target_container = container
                                        break
                        if target_container:
                            break

            if target_container:
                target_id = f"container:{target_container.id}"
            else:
                # Vérifier si c'est une IP d'hôte connu (mais pas de conteneur trouvé)
                # Dans ce cas, ne pas créer de nœud externe
                if conn.target_ip in host_by_ip:
                    continue

                # Connexion vraiment externe - limiter le nombre
                if external_count >= max_external:
                    continue
                external_id = f"external:{conn.target_ip}"
                if not any(n.id == external_id for n in nodes):
                    nodes.append(GraphNode(
                        id=external_id,
                        label=conn.target_ip,
                        type="external",
                        data={"ip": conn.target_ip}
                    ))
                    external_count += 1
                target_id = external_id

            if source_id and target_id and source_id != target_id:
                # Regrouper les connexions par source/target
                edge_key = (source_id, target_id)
                source_method = getattr(conn, 'source_method', 'proc_net')

                if edge_key not in edge_data:
                    edge_data[edge_key] = {
                        "protocol": conn.protocol,
                        "connection_type": conn.connection_type,
                        "source_methods": set(),
                    }

                edge_data[edge_key]["source_methods"].add(source_method)

        # Créer les edges à partir des données agrégées
        for (source_id, target_id), data in edge_data.items():
            edge_id = f"conn:{source_id}:{target_id}"
            if edge_id not in seen_edges:
                seen_edges.add(edge_id)

                # Déterminer le source_method à afficher
                # Si les deux méthodes ont détecté, préférer tcpdump (plus informatif)
                source_methods = data["source_methods"]
                if "tcpdump" in source_methods and "proc_net" in source_methods:
                    display_method = "both"
                elif "tcpdump" in source_methods:
                    display_method = "tcpdump"
                else:
                    display_method = "proc_net"

                edges.append(GraphEdge(
                    id=edge_id,
                    source=source_id,
                    target=target_id,
                    type="connection",
                    data={
                        "protocol": data["protocol"],
                        "connection_type": data["connection_type"],
                        "source_method": display_method,
                    }
                ))

        logger.info(f"Graphe généré: {len(nodes)} noeuds, {len(edges)} liens")
        return GraphData(
            nodes=nodes,
            edges=edges,
            last_updated=datetime.utcnow(),
        )

    async def _get_hosts(
        self,
        include_offline: bool,
        host_filter: Optional[str],
        organization_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> list[Host]:
        """Récupère les hôtes avec filtrage multi-tenant."""
        # Si team_id est spécifié, filtrer par équipe
        if team_id:
            query = (
                select(Host)
                .join(TeamHost, TeamHost.host_id == Host.id)
                .where(and_(
                    TeamHost.team_id == team_id,
                    TeamHost.can_view == True
                ))
            )
        # Si organization_id est spécifié, filtrer par organisation
        elif organization_id:
            query = (
                select(Host)
                .join(OrganizationHost, OrganizationHost.host_id == Host.id)
                .where(OrganizationHost.organization_id == organization_id)
            )
        else:
            # Pas de filtrage multi-tenant
            query = select(Host)

        if not include_offline:
            # Considérer offline après 5 minutes sans nouvelles
            cutoff = datetime.utcnow() - timedelta(minutes=5)
            query = query.where(Host.last_seen >= cutoff)

        if host_filter:
            query = query.where(Host.hostname.ilike(f"%{host_filter}%"))

        result = await self.db.execute(query)
        return result.scalars().all()

    async def _get_containers(
        self,
        host_id: str,
        include_offline: bool,
        project_filter: Optional[str]
    ) -> list[Container]:
        """Récupère les conteneurs d'un hôte."""
        query = select(Container).where(Container.host_id == host_id)

        if not include_offline:
            query = query.where(Container.status == ContainerStatusEnum.RUNNING)

        if project_filter:
            query = query.where(Container.compose_project.ilike(f"%{project_filter}%"))

        result = await self.db.execute(query)
        return result.scalars().all()

    async def _find_container_by_service(
        self,
        host_id: str,
        project: Optional[str],
        service: str
    ) -> Optional[Container]:
        """Trouve un conteneur par son service compose."""
        if not project:
            return None

        query = select(Container).where(
            Container.host_id == host_id,
            Container.compose_project == project,
            Container.compose_service == service,
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_connections(self, host_ids: list[str]) -> list[Connection]:
        """Récupère les connexions des hôtes."""
        if not host_ids:
            return []

        query = select(Connection).where(
            Connection.source_host_id.in_(host_ids)
        )
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_host_summary(
        self,
        organization_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> list[dict]:
        """Retourne un résumé de tous les hôtes avec filtrage multi-tenant."""
        # Filtrer par équipe ou organisation si spécifié
        if team_id:
            query = (
                select(Host)
                .join(TeamHost, TeamHost.host_id == Host.id)
                .where(and_(
                    TeamHost.team_id == team_id,
                    TeamHost.can_view == True
                ))
            )
        elif organization_id:
            query = (
                select(Host)
                .join(OrganizationHost, OrganizationHost.host_id == Host.id)
                .where(OrganizationHost.organization_id == organization_id)
            )
        else:
            query = select(Host)

        result = await self.db.execute(query)
        hosts = result.scalars().all()

        summary = []
        for host in hosts:
            # Récupérer les conteneurs séparément
            containers_result = await self.db.execute(
                select(Container).where(Container.host_id == host.id)
            )
            containers = containers_result.scalars().all()

            running = sum(1 for c in containers if c.status == ContainerStatusEnum.RUNNING)
            total = len(containers)

            summary.append({
                "id": host.id,
                "hostname": host.hostname,
                "tailscale_ip": host.tailscale_ip,
                "is_online": host.is_online,
                "last_seen": host.last_seen.isoformat() if host.last_seen else None,
                "containers_running": running,
                "containers_total": total,
            })

        return summary
