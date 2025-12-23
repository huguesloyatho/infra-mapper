"""Serveur HTTP pour recevoir les commandes du backend."""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from typing import Callable, Optional
from functools import partial

logger = logging.getLogger(__name__)


class CommandHandler(BaseHTTPRequestHandler):
    """Handler HTTP pour les commandes."""

    def __init__(self, docker_collector, api_key: str, *args, **kwargs):
        self.docker_collector = docker_collector
        self.api_key = api_key
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """Override pour logger via notre logger."""
        logger.debug(f"HTTP: {format % args}")

    def _check_auth(self) -> bool:
        """Vérifie l'authentification via API key."""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            return token == self.api_key
        return False

    def _send_json(self, data: dict, status: int = 200):
        """Envoie une réponse JSON."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_json(self) -> Optional[dict]:
        """Lit le body JSON de la requête."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        try:
            body = self.rfile.read(content_length)
            return json.loads(body.decode())
        except Exception as e:
            logger.error(f"Erreur parsing JSON: {e}")
            return None

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self._send_json({"status": "ok"})
            return

        if not self._check_auth():
            self._send_json({"error": "Unauthorized"}, 401)
            return

        if self.path == "/containers":
            containers = self.docker_collector.collect_containers()
            self._send_json({
                "containers": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "status": c.status.value,
                        "image": c.image
                    }
                    for c in containers
                ]
            })
            return

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """Handle POST requests."""
        if not self._check_auth():
            self._send_json({"error": "Unauthorized"}, 401)
            return

        body = self._read_json()
        if body is None:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        # Container actions
        if self.path == "/containers/start":
            container_id = body.get("container_id")
            if not container_id:
                self._send_json({"error": "container_id required"}, 400)
                return
            result = self.docker_collector.start_container(container_id)
            self._send_json(result, 200 if result.get("success") else 400)
            return

        if self.path == "/containers/stop":
            container_id = body.get("container_id")
            timeout = body.get("timeout", 10)
            if not container_id:
                self._send_json({"error": "container_id required"}, 400)
                return
            result = self.docker_collector.stop_container(container_id, timeout)
            self._send_json(result, 200 if result.get("success") else 400)
            return

        if self.path == "/containers/restart":
            container_id = body.get("container_id")
            timeout = body.get("timeout", 10)
            if not container_id:
                self._send_json({"error": "container_id required"}, 400)
                return
            result = self.docker_collector.restart_container(container_id, timeout)
            self._send_json(result, 200 if result.get("success") else 400)
            return

        if self.path == "/containers/exec":
            container_id = body.get("container_id")
            command = body.get("command")
            timeout = body.get("timeout", 30)
            workdir = body.get("workdir")
            if not container_id or not command:
                self._send_json({"error": "container_id and command required"}, 400)
                return
            result = self.docker_collector.exec_container(
                container_id, command, timeout, workdir
            )
            self._send_json(result, 200 if result.get("success") else 400)
            return

        if self.path == "/containers/stats":
            container_id = body.get("container_id")
            if not container_id:
                self._send_json({"error": "container_id required"}, 400)
                return
            result = self.docker_collector.get_container_stats(container_id)
            self._send_json(result, 200 if result.get("success") else 400)
            return

        if self.path == "/containers/logs":
            container_id = body.get("container_id")
            lines = body.get("lines", 100)
            since_seconds = body.get("since_seconds", 300)
            if not container_id:
                self._send_json({"error": "container_id required"}, 400)
                return
            logs = self.docker_collector.get_container_logs(
                container_id, lines, since_seconds
            )
            self._send_json({
                "success": True,
                "logs": [
                    {
                        "timestamp": log.timestamp,
                        "stream": log.stream,
                        "message": log.message
                    }
                    for log in logs
                ]
            })
            return

        self._send_json({"error": "Not found"}, 404)


class CommandServer:
    """Serveur de commandes pour l'agent."""

    def __init__(
        self,
        docker_collector,
        api_key: str,
        host: str = "0.0.0.0",
        port: int = 8081
    ):
        self.docker_collector = docker_collector
        self.api_key = api_key
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[Thread] = None

    def start(self):
        """Démarre le serveur dans un thread séparé."""
        handler = partial(CommandHandler, self.docker_collector, self.api_key)
        self.server = HTTPServer((self.host, self.port), handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"Command server démarré sur {self.host}:{self.port}")

    def stop(self):
        """Arrête le serveur."""
        if self.server:
            self.server.shutdown()
            logger.info("Command server arrêté")
