"""
Tests unitaires pour NotificationService.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from db.models import (
    Alert, AlertChannel, AlertChannelType,
    AlertSeverity, AlertStatus,
)
from services.notification_service import NotificationService


pytestmark = pytest.mark.unit


@pytest.fixture
def notification_service():
    """Instance du NotificationService."""
    return NotificationService()


@pytest.fixture
def test_alert():
    """Alerte de test."""
    return Alert(
        id="test-alert-001",
        rule_id="test-rule-001",
        severity=AlertSeverity.WARNING,
        status=AlertStatus.ACTIVE,
        title="Test Alert Title",
        message="This is a test alert message",
        host_name="test-host",
        container_name="test-container",
        triggered_at=datetime.utcnow(),
    )


class TestNotificationServiceSlack:
    """Tests pour les notifications Slack."""

    async def test_send_slack_success(self, notification_service, test_alert, mock_aiohttp_session):
        """Test envoi Slack réussi."""
        channel = AlertChannel(
            id="slack-001",
            name="Slack Test",
            channel_type=AlertChannelType.SLACK,
            enabled=True,
            config={"webhook_url": "https://hooks.slack.com/services/test"},
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session):
            success, error = await notification_service._send_slack(channel, test_alert)

        assert success is True
        assert error is None

    async def test_send_slack_missing_webhook(self, notification_service, test_alert):
        """Test Slack sans webhook_url."""
        channel = AlertChannel(
            id="slack-001",
            name="Slack Test",
            channel_type=AlertChannelType.SLACK,
            enabled=True,
            config={},  # Pas de webhook_url
        )

        success, error = await notification_service._send_slack(channel, test_alert)

        assert success is False
        assert "webhook_url" in error.lower()


class TestNotificationServiceDiscord:
    """Tests pour les notifications Discord."""

    async def test_send_discord_success(self, notification_service, test_alert, mock_aiohttp_session):
        """Test envoi Discord réussi."""
        channel = AlertChannel(
            id="discord-001",
            name="Discord Test",
            channel_type=AlertChannelType.DISCORD,
            enabled=True,
            config={"webhook_url": "https://discord.com/api/webhooks/test"},
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session):
            success, error = await notification_service._send_discord(channel, test_alert)

        assert success is True
        assert error is None

    async def test_send_discord_missing_webhook(self, notification_service, test_alert):
        """Test Discord sans webhook_url."""
        channel = AlertChannel(
            id="discord-001",
            name="Discord Test",
            channel_type=AlertChannelType.DISCORD,
            enabled=True,
            config={},
        )

        success, error = await notification_service._send_discord(channel, test_alert)

        assert success is False
        assert "webhook_url" in error.lower()


class TestNotificationServiceTelegram:
    """Tests pour les notifications Telegram."""

    async def test_send_telegram_success(self, notification_service, test_alert, mock_aiohttp_session):
        """Test envoi Telegram réussi."""
        channel = AlertChannel(
            id="telegram-001",
            name="Telegram Test",
            channel_type=AlertChannelType.TELEGRAM,
            enabled=True,
            config={"bot_token": "123:ABC", "chat_id": "-123456789"},
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session):
            success, error = await notification_service._send_telegram(channel, test_alert)

        assert success is True
        assert error is None

    async def test_send_telegram_missing_config(self, notification_service, test_alert):
        """Test Telegram config incomplète."""
        channel = AlertChannel(
            id="telegram-001",
            name="Telegram Test",
            channel_type=AlertChannelType.TELEGRAM,
            enabled=True,
            config={"bot_token": "123:ABC"},  # Manque chat_id
        )

        success, error = await notification_service._send_telegram(channel, test_alert)

        assert success is False
        assert "chat_id" in error.lower()


class TestNotificationServiceNtfy:
    """Tests pour les notifications ntfy."""

    async def test_send_ntfy_success(self, notification_service, test_alert, mock_aiohttp_session):
        """Test envoi ntfy réussi."""
        channel = AlertChannel(
            id="ntfy-001",
            name="Ntfy Test",
            channel_type=AlertChannelType.NTFY,
            enabled=True,
            config={"server": "https://ntfy.sh", "topic": "test-alerts"},
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session):
            success, error = await notification_service._send_ntfy(channel, test_alert)

        assert success is True
        assert error is None

    async def test_send_ntfy_with_server_url(self, notification_service, test_alert, mock_aiohttp_session):
        """Test ntfy avec server_url au lieu de server."""
        channel = AlertChannel(
            id="ntfy-001",
            name="Ntfy Test",
            channel_type=AlertChannelType.NTFY,
            enabled=True,
            config={"server_url": "https://ntfy.example.com", "topic": "test-alerts"},
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session):
            success, error = await notification_service._send_ntfy(channel, test_alert)

        assert success is True

    async def test_send_ntfy_missing_topic(self, notification_service, test_alert):
        """Test ntfy sans topic."""
        channel = AlertChannel(
            id="ntfy-001",
            name="Ntfy Test",
            channel_type=AlertChannelType.NTFY,
            enabled=True,
            config={"server": "https://ntfy.sh"},  # Manque topic
        )

        success, error = await notification_service._send_ntfy(channel, test_alert)

        assert success is False
        assert "topic" in error.lower()


class TestNotificationServiceWebhook:
    """Tests pour les webhooks génériques."""

    async def test_send_webhook_success(self, notification_service, test_alert, mock_aiohttp_session):
        """Test envoi webhook réussi."""
        channel = AlertChannel(
            id="webhook-001",
            name="Webhook Test",
            channel_type=AlertChannelType.WEBHOOK,
            enabled=True,
            config={"url": "https://example.com/webhook"},
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session):
            success, error = await notification_service._send_webhook(channel, test_alert)

        assert success is True
        assert error is None

    async def test_send_webhook_missing_url(self, notification_service, test_alert):
        """Test webhook sans URL."""
        channel = AlertChannel(
            id="webhook-001",
            name="Webhook Test",
            channel_type=AlertChannelType.WEBHOOK,
            enabled=True,
            config={},
        )

        success, error = await notification_service._send_webhook(channel, test_alert)

        assert success is False
        assert "url" in error.lower()


class TestNotificationServiceDispatch:
    """Tests pour le dispatch des notifications."""

    async def test_send_notification_dispatches_correctly(self, notification_service, test_alert, mock_aiohttp_session):
        """Test que send_notification dispatche au bon canal."""
        channel = AlertChannel(
            id="slack-001",
            name="Slack Test",
            channel_type=AlertChannelType.SLACK,
            enabled=True,
            config={"webhook_url": "https://hooks.slack.com/test"},
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session):
            success, error = await notification_service.send_notification(channel, test_alert)

        assert success is True

    async def test_test_channel_creates_test_alert(self, notification_service, mock_aiohttp_session):
        """Test que test_channel crée une alerte de test."""
        channel = AlertChannel(
            id="slack-001",
            name="Slack Test",
            channel_type=AlertChannelType.SLACK,
            enabled=True,
            config={"webhook_url": "https://hooks.slack.com/test"},
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session):
            success, error = await notification_service.test_channel(channel)

        assert success is True
        assert error is None


class TestNotificationServiceFormatting:
    """Tests pour le formatage des messages."""

    def test_severity_emoji_mapping(self, notification_service):
        """Test mapping emoji par sévérité."""
        assert notification_service.SEVERITY_EMOJI[AlertSeverity.INFO] == "ℹ️"
        assert notification_service.SEVERITY_EMOJI[AlertSeverity.WARNING] == "⚠️"
        assert notification_service.SEVERITY_EMOJI[AlertSeverity.CRITICAL] == "🚨"

    def test_severity_color_mapping(self, notification_service):
        """Test mapping couleur par sévérité."""
        # Vérifie que chaque sévérité a une couleur définie
        assert notification_service.SEVERITY_COLOR[AlertSeverity.INFO] is not None
        assert notification_service.SEVERITY_COLOR[AlertSeverity.WARNING] is not None
        assert notification_service.SEVERITY_COLOR[AlertSeverity.CRITICAL] is not None
        # Vérifie le format des couleurs (hex)
        for color in notification_service.SEVERITY_COLOR.values():
            assert color.startswith("#")
            assert len(color) == 7
