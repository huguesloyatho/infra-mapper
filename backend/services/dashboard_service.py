"""Service de gestion des dashboards personnalisés."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Dashboard, DashboardNode
from models.schemas import (
    DashboardCreate,
    DashboardUpdate,
    DashboardResponse,
    NodePosition,
    GraphData,
)
from services.graph_service import GraphService

logger = logging.getLogger(__name__)

# Durée de rétention des nœuds disparus
NODE_RETENTION_DAYS = 7


class DashboardService:
    """Service de gestion des dashboards personnalisés."""

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db

    async def list_dashboards(self) -> list[DashboardResponse]:
        """Liste tous les dashboards."""
        query = select(Dashboard).order_by(Dashboard.name)
        result = await self.db.execute(query)
        dashboards = result.scalars().all()

        responses = []
        for d in dashboards:
            # Compter les nœuds visibles
            node_query = select(DashboardNode).where(
                DashboardNode.dashboard_id == d.id,
                DashboardNode.is_visible == True
            )
            node_result = await self.db.execute(node_query)
            node_count = len(node_result.scalars().all())

            responses.append(DashboardResponse(
                id=d.id,
                name=d.name,
                description=d.description,
                host_filter=d.host_filter,
                project_filter=d.project_filter,
                include_offline=d.include_offline,
                show_external=d.show_external,
                edge_filters=d.edge_filters or {},
                created_at=d.created_at,
                updated_at=d.updated_at,
                node_count=node_count,
            ))

        return responses

    async def get_dashboard(self, dashboard_id: str) -> Optional[Dashboard]:
        """Récupère un dashboard par son ID."""
        query = select(Dashboard).where(Dashboard.id == dashboard_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_dashboard(self, data: DashboardCreate) -> DashboardResponse:
        """Crée un nouveau dashboard."""
        dashboard = Dashboard(
            id=str(uuid.uuid4()),
            name=data.name,
            description=data.description,
            host_filter=data.host_filter,
            project_filter=data.project_filter,
            include_offline=data.include_offline,
            show_external=data.show_external,
            edge_filters=data.edge_filters.model_dump() if data.edge_filters else {},
        )

        self.db.add(dashboard)
        await self.db.commit()
        await self.db.refresh(dashboard)

        logger.info(f"Dashboard créé: {dashboard.name} ({dashboard.id})")

        return DashboardResponse(
            id=dashboard.id,
            name=dashboard.name,
            description=dashboard.description,
            host_filter=dashboard.host_filter,
            project_filter=dashboard.project_filter,
            include_offline=dashboard.include_offline,
            show_external=dashboard.show_external,
            edge_filters=dashboard.edge_filters or {},
            created_at=dashboard.created_at,
            updated_at=dashboard.updated_at,
            node_count=0,
        )

    async def update_dashboard(
        self,
        dashboard_id: str,
        data: DashboardUpdate
    ) -> Optional[DashboardResponse]:
        """Met à jour un dashboard."""
        dashboard = await self.get_dashboard(dashboard_id)
        if not dashboard:
            return None

        if data.name is not None:
            dashboard.name = data.name
        if data.description is not None:
            dashboard.description = data.description
        if data.host_filter is not None:
            dashboard.host_filter = data.host_filter
        if data.project_filter is not None:
            dashboard.project_filter = data.project_filter
        if data.include_offline is not None:
            dashboard.include_offline = data.include_offline
        if data.show_external is not None:
            dashboard.show_external = data.show_external
        if data.edge_filters is not None:
            dashboard.edge_filters = data.edge_filters.model_dump()

        await self.db.commit()
        await self.db.refresh(dashboard)

        # Compter les nœuds
        node_query = select(DashboardNode).where(
            DashboardNode.dashboard_id == dashboard.id,
            DashboardNode.is_visible == True
        )
        node_result = await self.db.execute(node_query)
        node_count = len(node_result.scalars().all())

        return DashboardResponse(
            id=dashboard.id,
            name=dashboard.name,
            description=dashboard.description,
            host_filter=dashboard.host_filter,
            project_filter=dashboard.project_filter,
            include_offline=dashboard.include_offline,
            show_external=dashboard.show_external,
            edge_filters=dashboard.edge_filters or {},
            created_at=dashboard.created_at,
            updated_at=dashboard.updated_at,
            node_count=node_count,
        )

    async def delete_dashboard(self, dashboard_id: str) -> bool:
        """Supprime un dashboard."""
        dashboard = await self.get_dashboard(dashboard_id)
        if not dashboard:
            return False

        await self.db.delete(dashboard)
        await self.db.commit()

        logger.info(f"Dashboard supprimé: {dashboard.name} ({dashboard_id})")
        return True

    async def get_positions(self, dashboard_id: str) -> dict[str, NodePosition]:
        """Récupère les positions des nœuds d'un dashboard."""
        query = select(DashboardNode).where(
            DashboardNode.dashboard_id == dashboard_id
        )
        result = await self.db.execute(query)
        nodes = result.scalars().all()

        positions = {}
        for node in nodes:
            positions[node.node_id] = NodePosition(
                node_id=node.node_id,
                x=node.position_x,
                y=node.position_y,
            )

        return positions

    async def save_positions(
        self,
        dashboard_id: str,
        positions: list[NodePosition],
        current_node_ids: set[str]
    ) -> int:
        """
        Sauvegarde les positions des nœuds.

        Args:
            dashboard_id: ID du dashboard
            positions: Liste des positions à sauvegarder
            current_node_ids: Set des IDs des nœuds actuellement visibles dans le graphe

        Returns:
            Nombre de positions sauvegardées
        """
        # Récupérer les nœuds existants
        query = select(DashboardNode).where(
            DashboardNode.dashboard_id == dashboard_id
        )
        result = await self.db.execute(query)
        existing_nodes = {n.node_id: n for n in result.scalars().all()}

        now = datetime.utcnow()
        saved_count = 0

        for pos in positions:
            if pos.node_id in existing_nodes:
                # Mettre à jour la position existante
                node = existing_nodes[pos.node_id]
                node.position_x = pos.x
                node.position_y = pos.y
                node.last_seen = now
                node.is_visible = pos.node_id in current_node_ids
            else:
                # Créer une nouvelle entrée
                node_type = "container" if pos.node_id.startswith("container:") else "external"
                node = DashboardNode(
                    dashboard_id=dashboard_id,
                    node_id=pos.node_id,
                    node_type=node_type,
                    position_x=pos.x,
                    position_y=pos.y,
                    last_seen=now,
                    is_visible=pos.node_id in current_node_ids,
                )
                self.db.add(node)
            saved_count += 1

        # Marquer les nœuds qui ne sont plus dans le graphe comme invisibles
        for node_id, node in existing_nodes.items():
            if node_id not in {p.node_id for p in positions}:
                if node_id not in current_node_ids:
                    node.is_visible = False

        await self.db.commit()

        logger.debug(f"Dashboard {dashboard_id}: {saved_count} positions sauvegardées")
        return saved_count

    async def get_graph_with_positions(
        self,
        dashboard_id: str
    ) -> tuple[GraphData, dict[str, NodePosition]]:
        """
        Récupère le graphe avec les positions sauvegardées.

        Returns:
            Tuple (GraphData, dict des positions)
        """
        dashboard = await self.get_dashboard(dashboard_id)
        if not dashboard:
            raise ValueError(f"Dashboard {dashboard_id} non trouvé")

        # Générer le graphe avec les filtres du dashboard
        graph_service = GraphService(self.db)
        graph = await graph_service.generate_graph(
            include_offline=dashboard.include_offline,
            host_filter=dashboard.host_filter,
            project_filter=dashboard.project_filter,
        )

        # Récupérer les positions sauvegardées
        positions = await self.get_positions(dashboard_id)

        # Mettre à jour la visibilité des nœuds sauvegardés
        current_node_ids = {n.id for n in graph.nodes}
        await self._update_node_visibility(dashboard_id, current_node_ids)

        return graph, positions

    async def _update_node_visibility(
        self,
        dashboard_id: str,
        current_node_ids: set[str]
    ):
        """Met à jour la visibilité des nœuds en fonction du graphe actuel."""
        query = select(DashboardNode).where(
            DashboardNode.dashboard_id == dashboard_id
        )
        result = await self.db.execute(query)
        nodes = result.scalars().all()

        now = datetime.utcnow()

        for node in nodes:
            if node.node_id in current_node_ids:
                node.is_visible = True
                node.last_seen = now
            else:
                node.is_visible = False

        await self.db.commit()

    async def purge_old_nodes(self) -> int:
        """
        Purge les nœuds disparus depuis plus de 7 jours.

        Returns:
            Nombre de nœuds purgés
        """
        cutoff = datetime.utcnow() - timedelta(days=NODE_RETENTION_DAYS)

        # Supprimer les nœuds invisibles depuis trop longtemps
        query = delete(DashboardNode).where(
            DashboardNode.is_visible == False,
            DashboardNode.last_seen < cutoff
        )
        result = await self.db.execute(query)
        await self.db.commit()

        purged = result.rowcount
        if purged > 0:
            logger.info(f"Purge dashboards: {purged} nœuds supprimés (> {NODE_RETENTION_DAYS} jours)")

        return purged
