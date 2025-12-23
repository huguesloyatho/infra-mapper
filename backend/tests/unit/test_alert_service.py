"""
Tests unitaires pour AlertService.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from db.models import (
    Host, Container, Alert, AlertRule, AlertChannel,
    AlertStatus, AlertSeverity, AlertRuleType, AlertChannelType,
    ContainerStatusEnum, HealthStatusEnum,
)
from services.alert_service import AlertService


pytestmark = pytest.mark.unit


class TestAlertServiceChannels:
    """Tests pour la gestion des canaux."""

    async def test_get_channels_empty(self, db_session):
        """Test récupération canaux vides."""
        service = AlertService(db_session)
        channels = await service.get_channels()
        assert channels == []

    async def test_get_channels_with_data(self, db_session, alert_channel_in_db):
        """Test récupération canaux avec données."""
        service = AlertService(db_session)
        channels = await service.get_channels()
        assert len(channels) == 1
        assert channels[0].id == alert_channel_in_db.id
        assert channels[0].name == "Test Slack Channel"

    async def test_create_channel(self, db_session):
        """Test création d'un canal."""
        service = AlertService(db_session)
        data = {
            "name": "Discord Test",
            "channel_type": AlertChannelType.DISCORD,
            "enabled": True,
            "config": {"webhook_url": "https://discord.com/api/webhooks/test"},
        }
        channel = await service.create_channel(data)

        assert channel.id is not None
        assert channel.name == "Discord Test"
        assert channel.channel_type == AlertChannelType.DISCORD
        assert channel.enabled is True

    async def test_update_channel(self, db_session, alert_channel_in_db):
        """Test mise à jour d'un canal."""
        service = AlertService(db_session)
        updated = await service.update_channel(
            alert_channel_in_db.id,
            {"name": "Updated Name", "enabled": False}
        )

        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.enabled is False

    async def test_update_channel_not_found(self, db_session):
        """Test mise à jour canal inexistant."""
        service = AlertService(db_session)
        result = await service.update_channel("nonexistent", {"name": "Test"})
        assert result is None

    async def test_delete_channel(self, db_session, alert_channel_in_db):
        """Test suppression d'un canal."""
        service = AlertService(db_session)
        result = await service.delete_channel(alert_channel_in_db.id)
        assert result is True

        # Vérifier que le canal n'existe plus
        channel = await service.get_channel(alert_channel_in_db.id)
        assert channel is None

    async def test_delete_channel_not_found(self, db_session):
        """Test suppression canal inexistant."""
        service = AlertService(db_session)
        result = await service.delete_channel("nonexistent")
        assert result is False


class TestAlertServiceRules:
    """Tests pour la gestion des règles."""

    async def test_get_rules_empty(self, db_session):
        """Test récupération règles vides."""
        service = AlertService(db_session)
        rules = await service.get_rules()
        assert rules == []

    async def test_get_rules_with_data(self, db_session, alert_rule_in_db):
        """Test récupération règles avec données."""
        service = AlertService(db_session)
        rules = await service.get_rules()
        assert len(rules) == 1
        assert rules[0].id == alert_rule_in_db.id

    async def test_create_rule(self, db_session):
        """Test création d'une règle."""
        service = AlertService(db_session)
        data = {
            "name": "Container Stopped Rule",
            "rule_type": AlertRuleType.CONTAINER_STOPPED,
            "severity": AlertSeverity.CRITICAL,
            "enabled": True,
            "config": {"exclude": ["backup-*"]},
        }
        rule = await service.create_rule(data)

        assert rule.id is not None
        assert rule.name == "Container Stopped Rule"
        assert rule.rule_type == AlertRuleType.CONTAINER_STOPPED
        assert rule.severity == AlertSeverity.CRITICAL

    async def test_update_rule(self, db_session, alert_rule_in_db):
        """Test mise à jour d'une règle."""
        service = AlertService(db_session)
        updated = await service.update_rule(
            alert_rule_in_db.id,
            {"name": "Updated Rule", "severity": AlertSeverity.CRITICAL}
        )

        assert updated is not None
        assert updated.name == "Updated Rule"
        assert updated.severity == AlertSeverity.CRITICAL

    async def test_delete_rule(self, db_session, alert_rule_in_db):
        """Test suppression d'une règle."""
        service = AlertService(db_session)
        result = await service.delete_rule(alert_rule_in_db.id)
        assert result is True


class TestAlertServiceAlerts:
    """Tests pour la gestion des alertes."""

    async def test_get_alerts_empty(self, db_session):
        """Test récupération alertes vides."""
        service = AlertService(db_session)
        alerts = await service.get_alerts()
        assert alerts == []

    async def test_get_alerts_with_data(self, db_session, alert_in_db):
        """Test récupération alertes avec données."""
        service = AlertService(db_session)
        alerts = await service.get_alerts()
        assert len(alerts) == 1
        assert alerts[0].id == alert_in_db.id

    async def test_get_alerts_with_status_filter(self, db_session, alert_in_db):
        """Test filtrage alertes par status."""
        service = AlertService(db_session)

        # Avec le bon status
        alerts = await service.get_alerts(status=AlertStatus.ACTIVE)
        assert len(alerts) == 1

        # Avec un status différent
        alerts = await service.get_alerts(status=AlertStatus.RESOLVED)
        assert len(alerts) == 0

    async def test_get_alerts_with_severity_filter(self, db_session, alert_in_db):
        """Test filtrage alertes par sévérité."""
        service = AlertService(db_session)

        alerts = await service.get_alerts(severity=AlertSeverity.WARNING)
        assert len(alerts) == 1

        alerts = await service.get_alerts(severity=AlertSeverity.CRITICAL)
        assert len(alerts) == 0

    async def test_acknowledge_alert(self, db_session, alert_in_db):
        """Test acquittement d'une alerte."""
        service = AlertService(db_session)
        alert = await service.acknowledge_alert(alert_in_db.id, user_id="user-123")

        assert alert is not None
        assert alert.status == AlertStatus.ACKNOWLEDGED
        assert alert.acknowledged_at is not None
        assert alert.acknowledged_by == "user-123"

    async def test_resolve_alert(self, db_session, alert_in_db):
        """Test résolution d'une alerte."""
        service = AlertService(db_session)
        alert = await service.resolve_alert(alert_in_db.id)

        assert alert is not None
        assert alert.status == AlertStatus.RESOLVED
        assert alert.resolved_at is not None

    async def test_delete_alert(self, db_session, alert_in_db):
        """Test suppression d'une alerte."""
        service = AlertService(db_session)
        result = await service.delete_alert(alert_in_db.id)
        assert result is True

    async def test_get_active_alerts_count(self, db_session, alert_in_db):
        """Test comptage alertes actives."""
        service = AlertService(db_session)
        counts = await service.get_active_alerts_count()

        assert counts["total"] == 1
        assert counts["warning"] == 1
        assert counts["critical"] == 0


class TestAlertServicePatternMatching:
    """Tests pour le matching de patterns."""

    async def test_matches_pattern_glob(self, db_session):
        """Test matching glob pattern."""
        service = AlertService(db_session)

        assert service._matches_pattern("prod-web-01", "prod-*") is True
        assert service._matches_pattern("dev-web-01", "prod-*") is False
        assert service._matches_pattern("nginx", "*nginx*") is True

    async def test_matches_pattern_regex(self, db_session):
        """Test matching regex pattern."""
        service = AlertService(db_session)

        assert service._matches_pattern("prod-web-01", "^prod-.*") is True
        assert service._matches_pattern("dev-web-01", "^prod-.*") is False

    async def test_matches_pattern_empty(self, db_session):
        """Test matching pattern vide."""
        service = AlertService(db_session)

        assert service._matches_pattern("anything", "") is True
        assert service._matches_pattern("anything", None) is True


class TestAlertServiceEvaluation:
    """Tests pour l'évaluation des règles."""

    async def test_evaluate_host_offline(self, db_session, alert_rule_in_db, host_in_db):
        """Test évaluation règle host_offline."""
        service = AlertService(db_session)

        # Host récent - pas d'alerte
        alerts = await service._evaluate_host_offline(alert_rule_in_db)
        assert len(alerts) == 0

        # Simuler host offline
        host_in_db.last_seen = datetime.utcnow() - timedelta(minutes=10)
        await db_session.commit()

        # Mock des notifications pour éviter les vraies requêtes HTTP
        with patch.object(service, '_send_notifications', new_callable=AsyncMock):
            alerts = await service._evaluate_host_offline(alert_rule_in_db)
            assert len(alerts) == 1
            assert "offline" in alerts[0].title.lower()

    async def test_evaluate_container_stopped(self, db_session, host_in_db):
        """Test évaluation règle container_stopped."""
        # Créer une règle container_stopped
        rule = AlertRule(
            id="test-rule-container",
            name="Container Stopped",
            rule_type=AlertRuleType.CONTAINER_STOPPED,
            severity=AlertSeverity.WARNING,
            enabled=True,
            config={},
        )
        db_session.add(rule)
        await db_session.commit()

        # Créer un container arrêté
        container = Container(
            id=f"{host_in_db.id}:stopped123",
            container_id="stopped123",
            host_id=host_in_db.id,
            name="stopped-container",
            image="nginx:latest",
            status=ContainerStatusEnum.STOPPED,
        )
        db_session.add(container)
        await db_session.commit()

        service = AlertService(db_session)

        with patch.object(service, '_send_notifications', new_callable=AsyncMock):
            alerts = await service._evaluate_container_stopped(rule)
            assert len(alerts) == 1
            assert "stopped-container" in alerts[0].title

    async def test_cooldown_prevents_duplicate_alerts(self, db_session, alert_rule_in_db, host_in_db, alert_in_db):
        """Test que le cooldown empêche les alertes dupliquées."""
        service = AlertService(db_session)

        # L'alerte existe déjà, le cooldown devrait empêcher une nouvelle
        is_in_cooldown = await service._is_in_cooldown(
            alert_rule_in_db,
            host_id=host_in_db.id
        )
        assert is_in_cooldown is True

    async def test_no_cooldown_for_new_alert(self, db_session, alert_rule_in_db, host_in_db):
        """Test pas de cooldown pour nouvelle alerte."""
        service = AlertService(db_session)

        is_in_cooldown = await service._is_in_cooldown(
            alert_rule_in_db,
            host_id=host_in_db.id
        )
        assert is_in_cooldown is False
