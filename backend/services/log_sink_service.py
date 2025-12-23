"""Service pour la gestion des puits de logs externes."""

import asyncio
import json
import logging
import socket
import ssl
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import LogSink, LogSinkType, ContainerLog

logger = logging.getLogger(__name__)


class LogSinkService:
    """Service pour configurer et envoyer les logs vers des puits externes."""

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_sink(
        self,
        name: str,
        sink_type: LogSinkType,
        url: str,
        port: Optional[int] = None,
        auth_type: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        config: Optional[Dict] = None,
        filter_hosts: Optional[List[str]] = None,
        filter_containers: Optional[List[str]] = None,
        filter_streams: Optional[List[str]] = None,
        tls_enabled: bool = False,
        tls_verify: bool = True,
        batch_size: int = 100,
        flush_interval: int = 5,
        enabled: bool = True,
    ) -> LogSink:
        """Cree un nouveau puits de logs."""
        sink = LogSink(
            id=str(uuid.uuid4()),
            name=name,
            type=sink_type,
            url=url,
            port=port,
            auth_type=auth_type,
            username=username,
            password=password,
            api_key=api_key,
            token=token,
            config=config or {},
            filter_hosts=filter_hosts or [],
            filter_containers=filter_containers or [],
            filter_streams=filter_streams or [],
            tls_enabled=tls_enabled,
            tls_verify=tls_verify,
            batch_size=batch_size,
            flush_interval=flush_interval,
            enabled=enabled,
        )
        self.db.add(sink)
        await self.db.commit()
        await self.db.refresh(sink)
        return sink

    async def get_sink(self, sink_id: str) -> Optional[LogSink]:
        """Recupere un puits par son ID."""
        result = await self.db.execute(
            select(LogSink).where(LogSink.id == sink_id)
        )
        return result.scalar_one_or_none()

    async def list_sinks(self, enabled_only: bool = False) -> List[LogSink]:
        """Liste tous les puits de logs."""
        query = select(LogSink)
        if enabled_only:
            query = query.where(LogSink.enabled == True)
        query = query.order_by(LogSink.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_sink(
        self,
        sink_id: str,
        **kwargs
    ) -> Optional[LogSink]:
        """Met a jour un puits de logs."""
        sink = await self.get_sink(sink_id)
        if not sink:
            return None

        for key, value in kwargs.items():
            if hasattr(sink, key) and value is not None:
                setattr(sink, key, value)

        await self.db.commit()
        await self.db.refresh(sink)
        return sink

    async def delete_sink(self, sink_id: str) -> bool:
        """Supprime un puits de logs."""
        sink = await self.get_sink(sink_id)
        if not sink:
            return False

        await self.db.delete(sink)
        await self.db.commit()
        return True

    async def toggle_sink(self, sink_id: str) -> Optional[LogSink]:
        """Active/desactive un puits de logs."""
        sink = await self.get_sink(sink_id)
        if not sink:
            return None

        sink.enabled = not sink.enabled
        await self.db.commit()
        await self.db.refresh(sink)
        return sink

    # =========================================================================
    # Log Forwarding
    # =========================================================================

    async def forward_logs(
        self,
        logs: List[Dict[str, Any]],
        host_id: str,
    ) -> Dict[str, Any]:
        """
        Envoie les logs vers tous les puits actifs.

        Args:
            logs: Liste des logs a envoyer
            host_id: ID du host source

        Returns:
            Statistiques d'envoi
        """
        sinks = await self.list_sinks(enabled_only=True)
        if not sinks:
            return {"forwarded": 0, "sinks": 0}

        results = {"forwarded": 0, "sinks": len(sinks), "errors": []}

        for sink in sinks:
            # Filtrer les logs selon la config du sink
            filtered_logs = self._filter_logs(logs, sink, host_id)
            if not filtered_logs:
                continue

            try:
                success = await self._send_to_sink(sink, filtered_logs)
                if success:
                    results["forwarded"] += len(filtered_logs)
                    await self._update_sink_stats(sink.id, success=True, count=len(filtered_logs))
                else:
                    results["errors"].append({"sink": sink.name, "error": "Send failed"})
            except Exception as e:
                logger.error(f"Erreur envoi vers {sink.name}: {e}")
                results["errors"].append({"sink": sink.name, "error": str(e)})
                await self._update_sink_stats(sink.id, success=False, error=str(e))

        return results

    def _filter_logs(
        self,
        logs: List[Dict[str, Any]],
        sink: LogSink,
        host_id: str,
    ) -> List[Dict[str, Any]]:
        """Filtre les logs selon la configuration du sink."""
        # Filtre par host
        if sink.filter_hosts and host_id not in sink.filter_hosts:
            return []

        filtered = []
        for log in logs:
            # Filtre par container
            if sink.filter_containers:
                container_id = log.get("container_id", "")
                if container_id not in sink.filter_containers:
                    continue

            # Filtre par stream
            if sink.filter_streams:
                stream = log.get("stream", "stdout")
                if stream not in sink.filter_streams:
                    continue

            filtered.append(log)

        return filtered

    async def _send_to_sink(
        self,
        sink: LogSink,
        logs: List[Dict[str, Any]],
    ) -> bool:
        """Envoie les logs vers un puits specifique."""
        sender_map = {
            LogSinkType.GRAYLOG: self._send_graylog,
            LogSinkType.OPENOBSERVE: self._send_openobserve,
            LogSinkType.LOKI: self._send_loki,
            LogSinkType.ELASTICSEARCH: self._send_elasticsearch,
            LogSinkType.SPLUNK: self._send_splunk,
            LogSinkType.SYSLOG: self._send_syslog,
            LogSinkType.WEBHOOK: self._send_webhook,
        }

        sender = sender_map.get(sink.type)
        if not sender:
            logger.error(f"Type de sink non supporte: {sink.type}")
            return False

        return await sender(sink, logs)

    async def _update_sink_stats(
        self,
        sink_id: str,
        success: bool,
        count: int = 0,
        error: Optional[str] = None,
    ):
        """Met a jour les statistiques du sink."""
        if success:
            await self.db.execute(
                update(LogSink)
                .where(LogSink.id == sink_id)
                .values(
                    last_success=datetime.utcnow(),
                    logs_sent=LogSink.logs_sent + count,
                )
            )
        else:
            await self.db.execute(
                update(LogSink)
                .where(LogSink.id == sink_id)
                .values(
                    last_error=datetime.utcnow(),
                    last_error_message=error,
                    errors_count=LogSink.errors_count + 1,
                )
            )
        await self.db.commit()

    # =========================================================================
    # Sink-specific senders
    # =========================================================================

    async def _send_graylog(
        self,
        sink: LogSink,
        logs: List[Dict[str, Any]],
    ) -> bool:
        """Envoie vers Graylog en format GELF."""
        config = sink.config or {}
        facility = config.get("facility", "infra-mapper")
        gelf_version = config.get("version", "1.1")

        messages = []
        for log in logs:
            gelf_msg = {
                "version": gelf_version,
                "host": log.get("hostname", "unknown"),
                "short_message": log.get("message", "")[:250],
                "full_message": log.get("message", ""),
                "timestamp": self._parse_timestamp(log.get("timestamp")),
                "level": 3 if log.get("stream") == "stderr" else 6,
                "facility": facility,
                "_container_id": log.get("container_id", ""),
                "_container_name": log.get("container_name", ""),
                "_stream": log.get("stream", "stdout"),
            }
            messages.append(gelf_msg)

        url = f"{sink.url}:{sink.port or 12201}/gelf"
        return await self._http_post(sink, url, messages)

    async def _send_openobserve(
        self,
        sink: LogSink,
        logs: List[Dict[str, Any]],
    ) -> bool:
        """Envoie vers OpenObserve."""
        config = sink.config or {}
        org = config.get("org", "default")
        stream = config.get("stream", "logs")

        formatted_logs = []
        for log in logs:
            formatted_logs.append({
                "timestamp": log.get("timestamp"),
                "message": log.get("message", ""),
                "stream": log.get("stream", "stdout"),
                "container_id": log.get("container_id", ""),
                "container_name": log.get("container_name", ""),
                "hostname": log.get("hostname", ""),
                "level": "error" if log.get("stream") == "stderr" else "info",
            })

        url = f"{sink.url}/api/{org}/{stream}/_json"
        return await self._http_post(sink, url, formatted_logs)

    async def _send_loki(
        self,
        sink: LogSink,
        logs: List[Dict[str, Any]],
    ) -> bool:
        """Envoie vers Grafana Loki."""
        config = sink.config or {}
        labels = config.get("labels", {"app": "infra-mapper"})

        # Grouper les logs par labels
        streams = {}
        for log in logs:
            # Labels pour ce log
            log_labels = {
                **labels,
                "container": log.get("container_name", "unknown"),
                "host": log.get("hostname", "unknown"),
                "stream": log.get("stream", "stdout"),
            }
            label_key = json.dumps(log_labels, sort_keys=True)

            if label_key not in streams:
                streams[label_key] = {
                    "stream": log_labels,
                    "values": []
                }

            # Loki attend timestamp en nanosecondes
            ts = self._parse_timestamp(log.get("timestamp"))
            ts_ns = str(int(ts * 1_000_000_000))
            streams[label_key]["values"].append([ts_ns, log.get("message", "")])

        payload = {"streams": list(streams.values())}
        url = f"{sink.url}/loki/api/v1/push"

        headers = {"Content-Type": "application/json"}
        if config.get("tenant_id"):
            headers["X-Scope-OrgID"] = config["tenant_id"]

        return await self._http_post(sink, url, payload, extra_headers=headers)

    async def _send_elasticsearch(
        self,
        sink: LogSink,
        logs: List[Dict[str, Any]],
    ) -> bool:
        """Envoie vers Elasticsearch."""
        config = sink.config or {}
        index = config.get("index", "infra-mapper-logs")

        # Format bulk
        bulk_data = []
        for log in logs:
            # Action
            bulk_data.append(json.dumps({"index": {"_index": index}}))
            # Document
            doc = {
                "@timestamp": log.get("timestamp"),
                "message": log.get("message", ""),
                "stream": log.get("stream", "stdout"),
                "container_id": log.get("container_id", ""),
                "container_name": log.get("container_name", ""),
                "hostname": log.get("hostname", ""),
            }
            bulk_data.append(json.dumps(doc))

        url = f"{sink.url}/_bulk"
        body = "\n".join(bulk_data) + "\n"

        return await self._http_post(
            sink, url, body,
            content_type="application/x-ndjson",
            is_raw=True
        )

    async def _send_splunk(
        self,
        sink: LogSink,
        logs: List[Dict[str, Any]],
    ) -> bool:
        """Envoie vers Splunk HEC."""
        config = sink.config or {}
        source = config.get("source", "infra-mapper")
        sourcetype = config.get("sourcetype", "docker:logs")
        index = config.get("index", "main")

        events = []
        for log in logs:
            events.append({
                "time": self._parse_timestamp(log.get("timestamp")),
                "source": source,
                "sourcetype": sourcetype,
                "index": index,
                "event": {
                    "message": log.get("message", ""),
                    "stream": log.get("stream", "stdout"),
                    "container_id": log.get("container_id", ""),
                    "container_name": log.get("container_name", ""),
                    "hostname": log.get("hostname", ""),
                }
            })

        url = f"{sink.url}/services/collector/event"
        headers = {"Authorization": f"Splunk {sink.token or sink.api_key}"}

        return await self._http_post(sink, url, events, extra_headers=headers)

    async def _send_syslog(
        self,
        sink: LogSink,
        logs: List[Dict[str, Any]],
    ) -> bool:
        """Envoie vers un serveur Syslog."""
        config = sink.config or {}
        protocol = config.get("protocol", "tcp").lower()
        facility = config.get("facility", 1)  # user-level

        try:
            for log in logs:
                severity = 3 if log.get("stream") == "stderr" else 6  # err vs info
                priority = facility * 8 + severity

                # Format RFC 5424
                timestamp = log.get("timestamp", datetime.utcnow().isoformat())
                hostname = log.get("hostname", "-")
                app_name = log.get("container_name", "infra-mapper")
                msg = log.get("message", "")

                syslog_msg = f"<{priority}>1 {timestamp} {hostname} {app_name} - - - {msg}"

                if protocol == "udp":
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.sendto(syslog_msg.encode(), (sink.url, sink.port or 514))
                    sock.close()
                else:  # tcp
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    if sink.tls_enabled:
                        context = ssl.create_default_context()
                        if not sink.tls_verify:
                            context.check_hostname = False
                            context.verify_mode = ssl.CERT_NONE
                        sock = context.wrap_socket(sock, server_hostname=sink.url)
                    sock.connect((sink.url, sink.port or 514))
                    sock.send((syslog_msg + "\n").encode())
                    sock.close()

            return True
        except Exception as e:
            logger.error(f"Erreur syslog: {e}")
            return False

    async def _send_webhook(
        self,
        sink: LogSink,
        logs: List[Dict[str, Any]],
    ) -> bool:
        """Envoie vers un webhook generique."""
        config = sink.config or {}
        method = config.get("method", "POST").upper()
        wrap_in_array = config.get("wrap_in_array", True)

        payload = logs if wrap_in_array else {"logs": logs}
        return await self._http_post(sink, sink.url, payload)

    # =========================================================================
    # HTTP Helper
    # =========================================================================

    async def _http_post(
        self,
        sink: LogSink,
        url: str,
        data: Any,
        extra_headers: Optional[Dict] = None,
        content_type: str = "application/json",
        is_raw: bool = False,
    ) -> bool:
        """Effectue une requete HTTP POST."""
        headers = {"Content-Type": content_type}

        # Auth
        auth = None
        if sink.auth_type == "basic" and sink.username:
            auth = (sink.username, sink.password or "")
        elif sink.auth_type == "token" and sink.token:
            headers["Authorization"] = f"Bearer {sink.token}"
        elif sink.auth_type == "api_key" and sink.api_key:
            headers["Authorization"] = f"ApiKey {sink.api_key}"

        if extra_headers:
            headers.update(extra_headers)

        try:
            async with httpx.AsyncClient(
                verify=sink.tls_verify,
                timeout=30.0,
            ) as client:
                if is_raw:
                    response = await client.post(url, content=data, headers=headers, auth=auth)
                else:
                    response = await client.post(url, json=data, headers=headers, auth=auth)

                if response.status_code >= 400:
                    logger.error(f"HTTP {response.status_code} de {sink.name}: {response.text[:200]}")
                    return False

                return True
        except Exception as e:
            logger.error(f"Erreur HTTP vers {sink.name}: {e}")
            return False

    def _parse_timestamp(self, ts: Any) -> float:
        """Parse un timestamp en float (seconds since epoch)."""
        if ts is None:
            return datetime.utcnow().timestamp()
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, datetime):
            return ts.timestamp()
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return dt.timestamp()
            except:
                return datetime.utcnow().timestamp()
        return datetime.utcnow().timestamp()

    # =========================================================================
    # Test Connection
    # =========================================================================

    async def test_sink(self, sink_id: str) -> Dict[str, Any]:
        """Teste la connexion a un puits de logs."""
        sink = await self.get_sink(sink_id)
        if not sink:
            return {"success": False, "error": "Sink not found"}

        # Log de test
        test_log = {
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Test message from Infra-Mapper at {datetime.utcnow()}",
            "stream": "stdout",
            "container_id": "test-container",
            "container_name": "infra-mapper-test",
            "hostname": "infra-mapper",
        }

        try:
            success = await self._send_to_sink(sink, [test_log])
            if success:
                await self._update_sink_stats(sink.id, success=True, count=1)
                return {"success": True, "message": "Test log sent successfully"}
            else:
                return {"success": False, "error": "Failed to send test log"}
        except Exception as e:
            error_msg = str(e)
            await self._update_sink_stats(sink.id, success=False, error=error_msg)
            return {"success": False, "error": error_msg}
