"""Routes API pour la gestion des puits de logs externes."""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from db.models import LogSinkType
from services.log_sink_service import LogSinkService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/log-sinks", tags=["log-sinks"])


# =============================================================================
# Schemas
# =============================================================================

class LogSinkCreate(BaseModel):
    """Schema pour creer un puits de logs."""
    name: str
    type: LogSinkType
    url: str
    port: Optional[int] = None
    auth_type: Optional[str] = None  # none, basic, token, api_key
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    token: Optional[str] = None
    config: Optional[dict] = Field(default_factory=dict)
    filter_hosts: Optional[List[str]] = Field(default_factory=list)
    filter_containers: Optional[List[str]] = Field(default_factory=list)
    filter_streams: Optional[List[str]] = Field(default_factory=list)
    tls_enabled: bool = False
    tls_verify: bool = True
    batch_size: int = 100
    flush_interval: int = 5
    enabled: bool = True


class LogSinkUpdate(BaseModel):
    """Schema pour mettre a jour un puits de logs."""
    name: Optional[str] = None
    url: Optional[str] = None
    port: Optional[int] = None
    auth_type: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    token: Optional[str] = None
    config: Optional[dict] = None
    filter_hosts: Optional[List[str]] = None
    filter_containers: Optional[List[str]] = None
    filter_streams: Optional[List[str]] = None
    tls_enabled: Optional[bool] = None
    tls_verify: Optional[bool] = None
    batch_size: Optional[int] = None
    flush_interval: Optional[int] = None
    enabled: Optional[bool] = None


class LogSinkResponse(BaseModel):
    """Schema de reponse pour un puits de logs."""
    id: str
    name: str
    type: str
    url: str
    port: Optional[int]
    auth_type: Optional[str]
    username: Optional[str]
    config: dict
    filter_hosts: List[str]
    filter_containers: List[str]
    filter_streams: List[str]
    tls_enabled: bool
    tls_verify: bool
    batch_size: int
    flush_interval: int
    enabled: bool
    last_success: Optional[str]
    last_error: Optional[str]
    last_error_message: Optional[str]
    logs_sent: int
    errors_count: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class LogSinkTestResponse(BaseModel):
    """Response pour le test d'un sink."""
    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


class LogSinkTypesResponse(BaseModel):
    """Liste des types de puits supportes."""
    types: List[dict]


# =============================================================================
# Helper functions
# =============================================================================

def sink_to_response(sink) -> dict:
    """Convertit un LogSink en dict de reponse."""
    return {
        "id": sink.id,
        "name": sink.name,
        "type": sink.type.value if sink.type else None,
        "url": sink.url,
        "port": sink.port,
        "auth_type": sink.auth_type,
        "username": sink.username,
        # Ne pas renvoyer password/api_key/token
        "config": sink.config or {},
        "filter_hosts": sink.filter_hosts or [],
        "filter_containers": sink.filter_containers or [],
        "filter_streams": sink.filter_streams or [],
        "tls_enabled": sink.tls_enabled,
        "tls_verify": sink.tls_verify,
        "batch_size": sink.batch_size,
        "flush_interval": sink.flush_interval,
        "enabled": sink.enabled,
        "last_success": sink.last_success.isoformat() if sink.last_success else None,
        "last_error": sink.last_error.isoformat() if sink.last_error else None,
        "last_error_message": sink.last_error_message,
        "logs_sent": sink.logs_sent or 0,
        "errors_count": sink.errors_count or 0,
        "created_at": sink.created_at.isoformat() if sink.created_at else None,
        "updated_at": sink.updated_at.isoformat() if sink.updated_at else None,
    }


# =============================================================================
# Routes
# =============================================================================

@router.get("/types", response_model=LogSinkTypesResponse)
async def get_sink_types():
    """Retourne la liste des types de puits supportes avec leur configuration."""
    types = [
        {
            "id": "graylog",
            "name": "Graylog",
            "description": "Graylog GELF input",
            "default_port": 12201,
            "config_fields": [
                {"name": "facility", "type": "string", "default": "infra-mapper"},
                {"name": "version", "type": "string", "default": "1.1"},
            ],
            "auth_types": ["none", "basic"],
        },
        {
            "id": "openobserve",
            "name": "OpenObserve",
            "description": "OpenObserve HTTP API",
            "default_port": 5080,
            "config_fields": [
                {"name": "org", "type": "string", "default": "default"},
                {"name": "stream", "type": "string", "default": "logs"},
            ],
            "auth_types": ["basic", "token"],
        },
        {
            "id": "loki",
            "name": "Grafana Loki",
            "description": "Grafana Loki push API",
            "default_port": 3100,
            "config_fields": [
                {"name": "tenant_id", "type": "string", "default": ""},
                {"name": "labels", "type": "json", "default": {"app": "infra-mapper"}},
            ],
            "auth_types": ["none", "basic", "token"],
        },
        {
            "id": "elasticsearch",
            "name": "Elasticsearch",
            "description": "Elasticsearch bulk API",
            "default_port": 9200,
            "config_fields": [
                {"name": "index", "type": "string", "default": "infra-mapper-logs"},
            ],
            "auth_types": ["none", "basic", "api_key"],
        },
        {
            "id": "splunk",
            "name": "Splunk",
            "description": "Splunk HTTP Event Collector",
            "default_port": 8088,
            "config_fields": [
                {"name": "source", "type": "string", "default": "infra-mapper"},
                {"name": "sourcetype", "type": "string", "default": "docker:logs"},
                {"name": "index", "type": "string", "default": "main"},
            ],
            "auth_types": ["token"],
        },
        {
            "id": "syslog",
            "name": "Syslog",
            "description": "Syslog server (TCP/UDP)",
            "default_port": 514,
            "config_fields": [
                {"name": "protocol", "type": "select", "options": ["tcp", "udp"], "default": "tcp"},
                {"name": "facility", "type": "number", "default": 1},
            ],
            "auth_types": ["none"],
        },
        {
            "id": "webhook",
            "name": "Webhook",
            "description": "Generic HTTP webhook",
            "default_port": None,
            "config_fields": [
                {"name": "method", "type": "select", "options": ["POST", "PUT"], "default": "POST"},
                {"name": "wrap_in_array", "type": "boolean", "default": True},
            ],
            "auth_types": ["none", "basic", "token", "api_key"],
        },
    ]
    return {"types": types}


@router.get("")
async def list_sinks(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Liste tous les puits de logs configures."""
    service = LogSinkService(db)
    sinks = await service.list_sinks(enabled_only=enabled_only)
    return [sink_to_response(s) for s in sinks]


@router.post("", response_model=LogSinkResponse)
async def create_sink(
    data: LogSinkCreate,
    db: AsyncSession = Depends(get_db),
):
    """Cree un nouveau puits de logs."""
    try:
        service = LogSinkService(db)
        sink = await service.create_sink(
            name=data.name,
            sink_type=data.type,
            url=data.url,
            port=data.port,
            auth_type=data.auth_type,
            username=data.username,
            password=data.password,
            api_key=data.api_key,
            token=data.token,
            config=data.config,
            filter_hosts=data.filter_hosts,
            filter_containers=data.filter_containers,
            filter_streams=data.filter_streams,
            tls_enabled=data.tls_enabled,
            tls_verify=data.tls_verify,
            batch_size=data.batch_size,
            flush_interval=data.flush_interval,
            enabled=data.enabled,
        )
        return sink_to_response(sink)
    except Exception as e:
        logger.error(f"Erreur creation sink: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sink_id}", response_model=LogSinkResponse)
async def get_sink(
    sink_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Recupere un puits de logs par son ID."""
    service = LogSinkService(db)
    sink = await service.get_sink(sink_id)
    if not sink:
        raise HTTPException(status_code=404, detail="Sink not found")
    return sink_to_response(sink)


@router.put("/{sink_id}", response_model=LogSinkResponse)
async def update_sink(
    sink_id: str,
    data: LogSinkUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Met a jour un puits de logs."""
    service = LogSinkService(db)

    update_data = data.model_dump(exclude_unset=True)
    sink = await service.update_sink(sink_id, **update_data)

    if not sink:
        raise HTTPException(status_code=404, detail="Sink not found")

    return sink_to_response(sink)


@router.delete("/{sink_id}")
async def delete_sink(
    sink_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Supprime un puits de logs."""
    service = LogSinkService(db)
    success = await service.delete_sink(sink_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sink not found")
    return {"status": "deleted", "id": sink_id}


@router.post("/{sink_id}/toggle", response_model=LogSinkResponse)
async def toggle_sink(
    sink_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Active/desactive un puits de logs."""
    service = LogSinkService(db)
    sink = await service.toggle_sink(sink_id)
    if not sink:
        raise HTTPException(status_code=404, detail="Sink not found")
    return sink_to_response(sink)


@router.post("/{sink_id}/test", response_model=LogSinkTestResponse)
async def test_sink(
    sink_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Teste la connexion a un puits de logs."""
    service = LogSinkService(db)
    result = await service.test_sink(sink_id)
    return result


@router.post("/{sink_id}/reset-stats")
async def reset_sink_stats(
    sink_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Reinitialise les statistiques d'un puits."""
    service = LogSinkService(db)
    sink = await service.update_sink(
        sink_id,
        logs_sent=0,
        errors_count=0,
        last_success=None,
        last_error=None,
        last_error_message=None,
    )
    if not sink:
        raise HTTPException(status_code=404, detail="Sink not found")
    return {"status": "reset", "id": sink_id}
