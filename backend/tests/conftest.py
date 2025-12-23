"""
Fixtures et configuration globale pour les tests.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import MagicMock, AsyncMock

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

# Ajouter le répertoire backend au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import Base
from db.models import (
    Host, Container, Network, Connection, Vm,
    AlertChannel, AlertRule, Alert,
    AlertChannelType, AlertRuleType, AlertSeverity, AlertStatus,
    ContainerStatusEnum, HealthStatusEnum, VmStatusEnum, OsTypeEnum,
)
from db.auth_models import User, RoleEnum


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_engine():
    """Crée un moteur SQLite en mémoire pour les tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Crée une session de test."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


# =============================================================================
# Model Fixtures
# =============================================================================

@pytest.fixture
def sample_host() -> dict:
    """Données pour créer un Host de test."""
    return {
        "id": "test-host-001",
        "hostname": "test-server",
        "ip_addresses": ["192.168.1.100"],
        "tailscale_ip": "100.64.0.1",
        "docker_version": "24.0.0",
        "os_info": "Ubuntu 22.04",
        "is_online": True,
    }


@pytest.fixture
async def host_in_db(db_session: AsyncSession, sample_host: dict) -> Host:
    """Crée un Host dans la base de test."""
    host = Host(**sample_host)
    db_session.add(host)
    await db_session.commit()
    await db_session.refresh(host)
    return host


@pytest.fixture
def sample_container(sample_host: dict) -> dict:
    """Données pour créer un Container de test."""
    return {
        "id": f"{sample_host['id']}:abc123",
        "container_id": "abc123",
        "host_id": sample_host["id"],
        "name": "test-container",
        "image": "nginx:latest",
        "status": ContainerStatusEnum.RUNNING,
        "health": HealthStatusEnum.HEALTHY,
        "networks": ["bridge"],
        "ip_addresses": {"bridge": "172.17.0.2"},
        "ports": [{"container_port": 80, "host_port": 8080, "protocol": "tcp"}],
        "compose_project": "test-project",
        "compose_service": "web",
    }


@pytest.fixture
async def container_in_db(db_session: AsyncSession, host_in_db: Host, sample_container: dict) -> Container:
    """Crée un Container dans la base de test."""
    container = Container(**sample_container)
    db_session.add(container)
    await db_session.commit()
    await db_session.refresh(container)
    return container


@pytest.fixture
def sample_user() -> dict:
    """Données pour créer un User de test."""
    return {
        "id": "test-user-001",
        "username": "testuser",
        "email": "test@example.com",
        "password_hash": "$2b$12$dummy_hash_for_testing",
        "role": RoleEnum.ADMIN,
        "display_name": "Test User",
        "is_active": True,
    }


@pytest.fixture
async def user_in_db(db_session: AsyncSession, sample_user: dict) -> User:
    """Crée un User dans la base de test."""
    user = User(**sample_user)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def sample_alert_channel() -> dict:
    """Données pour créer un AlertChannel de test."""
    return {
        "id": "test-channel-001",
        "name": "Test Slack Channel",
        "channel_type": AlertChannelType.SLACK,
        "enabled": True,
        "config": {"webhook_url": "https://hooks.slack.com/test"},
        "severity_filter": [],
        "rule_type_filter": [],
    }


@pytest.fixture
async def alert_channel_in_db(db_session: AsyncSession, sample_alert_channel: dict) -> AlertChannel:
    """Crée un AlertChannel dans la base de test."""
    channel = AlertChannel(**sample_alert_channel)
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return channel


@pytest.fixture
def sample_alert_rule() -> dict:
    """Données pour créer une AlertRule de test."""
    return {
        "id": "test-rule-001",
        "name": "Test Host Offline Rule",
        "description": "Alert when host goes offline",
        "rule_type": AlertRuleType.HOST_OFFLINE,
        "severity": AlertSeverity.WARNING,
        "enabled": True,
        "config": {"timeout_minutes": 5},
        "cooldown_minutes": 15,
    }


@pytest.fixture
async def alert_rule_in_db(db_session: AsyncSession, sample_alert_rule: dict) -> AlertRule:
    """Crée une AlertRule dans la base de test."""
    rule = AlertRule(**sample_alert_rule)
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


@pytest.fixture
def sample_alert(sample_alert_rule: dict, sample_host: dict) -> dict:
    """Données pour créer une Alert de test."""
    return {
        "id": "test-alert-001",
        "rule_id": sample_alert_rule["id"],
        "severity": AlertSeverity.WARNING,
        "status": AlertStatus.ACTIVE,
        "title": "Host offline: test-server",
        "message": "Le host test-server n'a pas été vu depuis 5 minutes",
        "host_id": sample_host["id"],
        "host_name": sample_host["hostname"],
        "triggered_at": datetime.utcnow(),
    }


@pytest.fixture
async def alert_in_db(db_session: AsyncSession, alert_rule_in_db: AlertRule, host_in_db: Host, sample_alert: dict) -> Alert:
    """Crée une Alert dans la base de test."""
    alert = Alert(**sample_alert)
    db_session.add(alert)
    await db_session.commit()
    await db_session.refresh(alert)
    return alert


@pytest.fixture
def sample_vm() -> dict:
    """Données pour créer une VM de test."""
    return {
        "id": "test-vm-001",
        "name": "Test VM",
        "hostname": "test-vm",
        "ip_address": "192.168.1.200",
        "ssh_port": 22,
        "ssh_user": "root",
        "os_type": OsTypeEnum.UBUNTU,
        "status": VmStatusEnum.ONLINE,
        "is_auto_discovered": False,
        "tags": ["production", "web"],
    }


@pytest.fixture
async def vm_in_db(db_session: AsyncSession, sample_vm: dict) -> Vm:
    """Crée une VM dans la base de test."""
    vm = Vm(**sample_vm)
    db_session.add(vm)
    await db_session.commit()
    await db_session.refresh(vm)
    return vm


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_notification_service():
    """Mock du NotificationService."""
    mock = MagicMock()
    mock.send_notification = AsyncMock(return_value=(True, None))
    mock.test_channel = AsyncMock(return_value=(True, None))
    return mock


@pytest.fixture
def mock_aiohttp_session():
    """Mock d'une session aiohttp."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.text = AsyncMock(return_value="OK")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    return mock_session
