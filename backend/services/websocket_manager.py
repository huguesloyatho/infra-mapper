"""Gestionnaire de WebSocket pour les mises à jour temps réel."""

import logging
import json
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Gestionnaire de connexions WebSocket."""

    def __init__(self):
        """Initialise le gestionnaire."""
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accepte une nouvelle connexion WebSocket."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connecté. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Déconnecte un WebSocket."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket déconnecté. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Envoie un message à tous les clients connectés."""
        if not self.active_connections:
            return

        disconnected = set()
        message_json = json.dumps(message, default=str)

        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.warning(f"Erreur envoi WebSocket: {e}")
                disconnected.add(connection)

        # Nettoyer les connexions mortes
        self.active_connections -= disconnected

    async def broadcast_update(self, event_type: str, data: dict):
        """Envoie une notification de mise à jour."""
        await self.broadcast({
            "type": event_type,
            "data": data,
        })

    async def notify_host_update(self, host_id: str, hostname: str):
        """Notifie d'une mise à jour d'hôte."""
        await self.broadcast_update("host_update", {
            "host_id": host_id,
            "hostname": hostname,
        })

    async def notify_container_change(self, host_id: str, container_id: str, action: str):
        """Notifie d'un changement de conteneur."""
        await self.broadcast_update("container_change", {
            "host_id": host_id,
            "container_id": container_id,
            "action": action,  # added, updated, removed
        })

    async def notify_graph_refresh(self):
        """Notifie qu'il faut rafraîchir le graphe."""
        await self.broadcast_update("graph_refresh", {})

    async def notify_deployment_progress(
        self,
        vm_id: str,
        step: str,
        progress: int,
        message: str = None
    ):
        """Notifie de la progression du déploiement d'un agent."""
        await self.broadcast_update("deployment_progress", {
            "vm_id": vm_id,
            "step": step,
            "progress": progress,
            "message": message,
        })


# Instance globale
ws_manager = WebSocketManager()
