"""
Tests d'intégration pour l'API des alertes.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from main import app
from db.models import AlertChannelType, AlertRuleType, AlertSeverity


pytestmark = pytest.mark.integration


@pytest.fixture
async def async_client(test_engine):
    """Client HTTP async pour les tests."""
    from db import get_db
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestAlertChannelsAPI:
    """Tests pour les endpoints de canaux d'alerte."""

    async def test_list_channels_empty(self, async_client):
        """Test GET /api/v1/alerts/channels vide."""
        response = await async_client.get("/api/v1/alerts/channels")

        assert response.status_code == 200
        assert response.json() == []

    async def test_create_channel(self, async_client):
        """Test POST /api/v1/alerts/channels."""
        data = {
            "name": "Test Slack",
            "channel_type": "slack",
            "enabled": True,
            "config": {"webhook_url": "https://hooks.slack.com/test"},
        }

        response = await async_client.post("/api/v1/alerts/channels", json=data)

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "Test Slack"
        assert result["channel_type"] == "slack"
        assert result["id"] is not None

    async def test_get_channel(self, async_client):
        """Test GET /api/v1/alerts/channels/{id}."""
        # Créer d'abord
        create_data = {
            "name": "Test Channel",
            "channel_type": "discord",
            "config": {"webhook_url": "https://discord.com/test"},
        }
        create_response = await async_client.post("/api/v1/alerts/channels", json=create_data)
        channel_id = create_response.json()["id"]

        # Récupérer
        response = await async_client.get(f"/api/v1/alerts/channels/{channel_id}")

        assert response.status_code == 200
        assert response.json()["id"] == channel_id

    async def test_get_channel_not_found(self, async_client):
        """Test GET /api/v1/alerts/channels/{id} inexistant."""
        response = await async_client.get("/api/v1/alerts/channels/nonexistent")

        assert response.status_code == 404

    async def test_update_channel(self, async_client):
        """Test PUT /api/v1/alerts/channels/{id}."""
        # Créer
        create_data = {
            "name": "Original Name",
            "channel_type": "slack",
            "config": {"webhook_url": "https://hooks.slack.com/test"},
        }
        create_response = await async_client.post("/api/v1/alerts/channels", json=create_data)
        channel_id = create_response.json()["id"]

        # Mettre à jour
        update_data = {"name": "Updated Name", "enabled": False}
        response = await async_client.put(f"/api/v1/alerts/channels/{channel_id}", json=update_data)

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "Updated Name"
        assert result["enabled"] is False

    async def test_delete_channel(self, async_client):
        """Test DELETE /api/v1/alerts/channels/{id}."""
        # Créer
        create_data = {
            "name": "To Delete",
            "channel_type": "webhook",
            "config": {"url": "https://example.com/hook"},
        }
        create_response = await async_client.post("/api/v1/alerts/channels", json=create_data)
        channel_id = create_response.json()["id"]

        # Supprimer
        response = await async_client.delete(f"/api/v1/alerts/channels/{channel_id}")

        assert response.status_code == 200

        # Vérifier suppression
        get_response = await async_client.get(f"/api/v1/alerts/channels/{channel_id}")
        assert get_response.status_code == 404

    async def test_test_channel(self, async_client):
        """Test POST /api/v1/alerts/channels/{id}/test."""
        # Créer
        create_data = {
            "name": "Test Channel",
            "channel_type": "slack",
            "config": {"webhook_url": "https://hooks.slack.com/test"},
        }
        create_response = await async_client.post("/api/v1/alerts/channels", json=create_data)
        channel_id = create_response.json()["id"]

        # Tester (mock la notification)
        with patch("services.notification_service.NotificationService.test_channel", new_callable=AsyncMock) as mock:
            mock.return_value = (True, None)
            response = await async_client.post(f"/api/v1/alerts/channels/{channel_id}/test")

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True


class TestAlertRulesAPI:
    """Tests pour les endpoints de règles d'alerte."""

    async def test_list_rules_empty(self, async_client):
        """Test GET /api/v1/alerts/rules vide."""
        response = await async_client.get("/api/v1/alerts/rules")

        assert response.status_code == 200
        assert response.json() == []

    async def test_create_rule(self, async_client):
        """Test POST /api/v1/alerts/rules."""
        data = {
            "name": "Host Offline Rule",
            "rule_type": "host_offline",
            "severity": "warning",
            "enabled": True,
            "config": {"timeout_minutes": 5},
        }

        response = await async_client.post("/api/v1/alerts/rules", json=data)

        assert response.status_code == 200
        result = response.json()
        assert result["name"] == "Host Offline Rule"
        assert result["rule_type"] == "host_offline"

    async def test_update_rule(self, async_client):
        """Test PUT /api/v1/alerts/rules/{id}."""
        # Créer
        create_data = {
            "name": "Original Rule",
            "rule_type": "container_stopped",
            "severity": "warning",
        }
        create_response = await async_client.post("/api/v1/alerts/rules", json=create_data)
        rule_id = create_response.json()["id"]

        # Mettre à jour
        update_data = {"name": "Updated Rule", "severity": "critical"}
        response = await async_client.put(f"/api/v1/alerts/rules/{rule_id}", json=update_data)

        assert response.status_code == 200
        assert response.json()["severity"] == "critical"

    async def test_delete_rule(self, async_client):
        """Test DELETE /api/v1/alerts/rules/{id}."""
        # Créer
        create_data = {
            "name": "To Delete",
            "rule_type": "host_offline",
        }
        create_response = await async_client.post("/api/v1/alerts/rules", json=create_data)
        rule_id = create_response.json()["id"]

        # Supprimer
        response = await async_client.delete(f"/api/v1/alerts/rules/{rule_id}")

        assert response.status_code == 200


class TestAlertsAPI:
    """Tests pour les endpoints d'alertes."""

    async def test_list_alerts_empty(self, async_client):
        """Test GET /api/v1/alerts vide."""
        response = await async_client.get("/api/v1/alerts")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_active_alerts_count(self, async_client):
        """Test GET /api/v1/alerts/count."""
        response = await async_client.get("/api/v1/alerts/count")

        assert response.status_code == 200
        result = response.json()
        assert "total" in result
        assert "warning" in result
        assert "critical" in result
