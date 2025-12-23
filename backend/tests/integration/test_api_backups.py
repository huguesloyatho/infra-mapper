"""
Tests d'intégration pour l'API des backups.
"""

import pytest
import tempfile
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from main import app
from services.backup_service import BackupService


pytestmark = pytest.mark.integration


@pytest.fixture
async def async_client(test_engine, tmp_path):
    """Client HTTP async pour les tests avec backup dir temporaire."""
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

    # Utiliser un répertoire temporaire pour les backups
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    with patch.object(BackupService, 'BACKUP_DIR', backup_dir):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


class TestBackupsAPI:
    """Tests pour les endpoints de backup."""

    async def test_list_backups_empty(self, async_client):
        """Test GET /api/v1/backups vide."""
        response = await async_client.get("/api/v1/backups")

        assert response.status_code == 200
        assert response.json() == []

    async def test_create_backup(self, async_client):
        """Test POST /api/v1/backups."""
        response = await async_client.post("/api/v1/backups", json={"include_logs": False})

        assert response.status_code == 200
        result = response.json()
        assert "id" in result
        assert "filename" in result
        assert "size_bytes" in result
        assert "size_human" in result
        assert result["size_bytes"] > 0

    async def test_list_backups_after_create(self, async_client):
        """Test listing après création."""
        # Créer un backup
        await async_client.post("/api/v1/backups", json={})

        # Lister
        response = await async_client.get("/api/v1/backups")

        assert response.status_code == 200
        backups = response.json()
        assert len(backups) == 1

    async def test_get_backup(self, async_client):
        """Test GET /api/v1/backups/{id}."""
        # Créer
        create_response = await async_client.post("/api/v1/backups", json={})
        backup_id = create_response.json()["id"]

        # Récupérer
        response = await async_client.get(f"/api/v1/backups/{backup_id}")

        assert response.status_code == 200
        assert response.json()["id"] == backup_id

    async def test_get_backup_not_found(self, async_client):
        """Test GET /api/v1/backups/{id} inexistant."""
        response = await async_client.get("/api/v1/backups/nonexistent")

        assert response.status_code == 404

    async def test_delete_backup(self, async_client):
        """Test DELETE /api/v1/backups/{id}."""
        # Créer
        create_response = await async_client.post("/api/v1/backups", json={})
        backup_id = create_response.json()["id"]

        # Supprimer
        response = await async_client.delete(f"/api/v1/backups/{backup_id}")

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "deleted"

        # Vérifier suppression
        get_response = await async_client.get(f"/api/v1/backups/{backup_id}")
        assert get_response.status_code == 404

    async def test_cleanup_backups(self, async_client):
        """Test POST /api/v1/backups/cleanup."""
        response = await async_client.post("/api/v1/backups/cleanup", json={"retention_days": 30})

        assert response.status_code == 200
        result = response.json()
        assert "deleted_count" in result
        assert "retention_days" in result

    async def test_download_backup(self, async_client):
        """Test GET /api/v1/backups/{id}/download."""
        # Créer
        create_response = await async_client.post("/api/v1/backups", json={})
        backup_id = create_response.json()["id"]

        # Télécharger
        response = await async_client.get(f"/api/v1/backups/{backup_id}/download")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/gzip"

    async def test_restore_backup(self, async_client):
        """Test POST /api/v1/backups/{id}/restore."""
        # Créer
        create_response = await async_client.post("/api/v1/backups", json={})
        backup_id = create_response.json()["id"]

        # Restaurer
        response = await async_client.post(
            f"/api/v1/backups/{backup_id}/restore",
            json={"clear_existing": True}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert "restored" in result

    async def test_restore_backup_not_found(self, async_client):
        """Test restauration backup inexistant."""
        response = await async_client.post(
            "/api/v1/backups/nonexistent/restore",
            json={}
        )

        assert response.status_code == 404
