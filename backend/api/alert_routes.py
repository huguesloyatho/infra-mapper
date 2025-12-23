"""Routes API pour le système d'alerting."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from db.models import AlertStatus as DbAlertStatus, AlertSeverity as DbAlertSeverity
from models.schemas import (
    AlertChannelCreate,
    AlertChannelUpdate,
    AlertChannelResponse,
    AlertRuleCreate,
    AlertRuleUpdate,
    AlertRuleResponse,
    AlertResponse,
    AlertsCountResponse,
    AlertStatus,
    AlertSeverity,
)
from services.alert_service import AlertService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _channel_to_response(channel) -> AlertChannelResponse:
    """Convertit un canal DB en réponse API."""
    return AlertChannelResponse(
        id=channel.id,
        name=channel.name,
        channel_type=channel.channel_type.value,
        enabled=channel.enabled,
        config=channel.config or {},
        severity_filter=channel.severity_filter or [],
        rule_type_filter=channel.rule_type_filter or [],
        created_at=channel.created_at,
        updated_at=channel.updated_at,
        last_used_at=channel.last_used_at,
        last_error=channel.last_error,
    )


def _rule_to_response(rule) -> AlertRuleResponse:
    """Convertit une règle DB en réponse API."""
    return AlertRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        rule_type=rule.rule_type.value,
        severity=rule.severity.value,
        enabled=rule.enabled,
        config=rule.config or {},
        host_filter=rule.host_filter,
        container_filter=rule.container_filter,
        project_filter=rule.project_filter,
        cooldown_minutes=rule.cooldown_minutes,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _alert_to_response(alert) -> AlertResponse:
    """Convertit une alerte DB en réponse API."""
    return AlertResponse(
        id=alert.id,
        rule_id=alert.rule_id,
        severity=alert.severity.value,
        status=alert.status.value,
        title=alert.title,
        message=alert.message,
        host_id=alert.host_id,
        host_name=alert.host_name,
        container_id=alert.container_id,
        container_name=alert.container_name,
        context=alert.context or {},
        triggered_at=alert.triggered_at,
        resolved_at=alert.resolved_at,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
        notifications_sent=alert.notifications_sent or [],
    )


# =============================================================================
# Channels
# =============================================================================

@router.get("/channels", response_model=list[AlertChannelResponse])
async def list_channels(db: AsyncSession = Depends(get_db)):
    """Liste tous les canaux de notification."""
    service = AlertService(db)
    channels = await service.get_channels()
    return [_channel_to_response(c) for c in channels]


@router.get("/channels/{channel_id}", response_model=AlertChannelResponse)
async def get_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    """Récupère un canal par ID."""
    service = AlertService(db)
    channel = await service.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal non trouvé")
    return _channel_to_response(channel)


@router.post("/channels", response_model=AlertChannelResponse)
async def create_channel(data: AlertChannelCreate, db: AsyncSession = Depends(get_db)):
    """Crée un nouveau canal de notification."""
    service = AlertService(db)
    channel = await service.create_channel(data.model_dump())
    return _channel_to_response(channel)


@router.put("/channels/{channel_id}", response_model=AlertChannelResponse)
async def update_channel(
    channel_id: str,
    data: AlertChannelUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Met à jour un canal."""
    service = AlertService(db)
    channel = await service.update_channel(channel_id, data.model_dump(exclude_unset=True))
    if not channel:
        raise HTTPException(status_code=404, detail="Canal non trouvé")
    return _channel_to_response(channel)


@router.delete("/channels/{channel_id}")
async def delete_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    """Supprime un canal."""
    service = AlertService(db)
    if not await service.delete_channel(channel_id):
        raise HTTPException(status_code=404, detail="Canal non trouvé")
    return {"status": "deleted"}


@router.post("/channels/{channel_id}/test")
async def test_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    """Teste un canal de notification."""
    service = AlertService(db)
    success, error = await service.test_channel(channel_id)
    return {"success": success, "error": error}


# =============================================================================
# Rules
# =============================================================================

@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_rules(db: AsyncSession = Depends(get_db)):
    """Liste toutes les règles d'alerte."""
    service = AlertService(db)
    rules = await service.get_rules()
    return [_rule_to_response(r) for r in rules]


@router.get("/rules/{rule_id}", response_model=AlertRuleResponse)
async def get_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """Récupère une règle par ID."""
    service = AlertService(db)
    rule = await service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    return _rule_to_response(rule)


@router.post("/rules", response_model=AlertRuleResponse)
async def create_rule(data: AlertRuleCreate, db: AsyncSession = Depends(get_db)):
    """Crée une nouvelle règle d'alerte."""
    service = AlertService(db)
    rule = await service.create_rule(data.model_dump())
    return _rule_to_response(rule)


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_rule(
    rule_id: str,
    data: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Met à jour une règle."""
    service = AlertService(db)
    rule = await service.update_rule(rule_id, data.model_dump(exclude_unset=True))
    if not rule:
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    return _rule_to_response(rule)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """Supprime une règle."""
    service = AlertService(db)
    if not await service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Règle non trouvée")
    return {"status": "deleted"}


# =============================================================================
# Alerts
# =============================================================================

@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    status: Optional[AlertStatus] = None,
    severity: Optional[AlertSeverity] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Liste les alertes avec filtres optionnels."""
    service = AlertService(db)

    # Convertir les enums schema vers enums DB
    db_status = DbAlertStatus(status.value) if status else None
    db_severity = DbAlertSeverity(severity.value) if severity else None

    alerts = await service.get_alerts(
        status=db_status,
        severity=db_severity,
        limit=limit,
        offset=offset,
    )
    return [_alert_to_response(a) for a in alerts]


@router.get("/count", response_model=AlertsCountResponse)
async def count_alerts(db: AsyncSession = Depends(get_db)):
    """Compte les alertes actives par sévérité."""
    service = AlertService(db)
    counts = await service.get_active_alerts_count()
    return AlertsCountResponse(**counts)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Récupère une alerte par ID."""
    service = AlertService(db)
    alert = await service.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return _alert_to_response(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: str,
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Acquitte une alerte."""
    service = AlertService(db)
    alert = await service.acknowledge_alert(alert_id, user_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return _alert_to_response(alert)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Résout manuellement une alerte."""
    service = AlertService(db)
    alert = await service.resolve_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return _alert_to_response(alert)


@router.delete("/{alert_id}")
async def delete_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    """Supprime une alerte."""
    service = AlertService(db)
    if not await service.delete_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    return {"status": "deleted"}


@router.post("/evaluate")
async def evaluate_rules(db: AsyncSession = Depends(get_db)):
    """Force l'évaluation de toutes les règles (debug/test)."""
    service = AlertService(db)
    new_alerts = await service.evaluate_all_rules()
    return {
        "evaluated": True,
        "new_alerts": len(new_alerts),
        "alerts": [_alert_to_response(a) for a in new_alerts],
    }


@router.delete("/cleanup")
async def cleanup_old_alerts(days: int = 30, db: AsyncSession = Depends(get_db)):
    """Supprime les alertes résolues plus anciennes que X jours."""
    service = AlertService(db)
    count = await service.delete_old_alerts(days)
    return {"deleted": count}
