"""
Tests unitaires pour BackupService.
"""

import pytest
import json
import gzip
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from db.models import Host, Container, Vm
from services.backup_service import BackupService, BackupMetadata


pytestmark = pytest.mark.unit


@pytest.fixture
def temp_backup_dir(tmp_path):
    """Crée un répertoire temporaire pour les backups."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir


@pytest.fixture
def backup_service_with_temp_dir(db_session, temp_backup_dir):
    """BackupService avec répertoire temporaire."""
    service = BackupService(db_session)
    service.BACKUP_DIR = temp_backup_dir
    return service


class TestBackupServiceCreate:
    """Tests pour la création de backups."""

    async def test_create_backup_empty_db(self, backup_service_with_temp_dir, temp_backup_dir):
        """Test création backup avec DB vide."""
        service = backup_service_with_temp_dir

        metadata = await service.create_backup()

        assert metadata is not None
        assert metadata.id is not None
        assert metadata.filename.endswith(".json.gz")
        assert metadata.size_bytes > 0
        assert metadata.version == "1.0"

        # Vérifier que le fichier existe
        backup_file = temp_backup_dir / metadata.filename
        assert backup_file.exists()

        # Vérifier le contenu
        with gzip.open(backup_file, 'rt') as f:
            data = json.load(f)
            assert "metadata" in data
            assert "tables" in data

    async def test_create_backup_with_data(self, backup_service_with_temp_dir, host_in_db, container_in_db, temp_backup_dir):
        """Test création backup avec données."""
        service = backup_service_with_temp_dir

        metadata = await service.create_backup()

        assert metadata.tables.get("hosts", 0) >= 1
        assert metadata.tables.get("containers", 0) >= 1

        # Vérifier le contenu du backup
        backup_file = temp_backup_dir / metadata.filename
        with gzip.open(backup_file, 'rt') as f:
            data = json.load(f)
            assert len(data["tables"]["hosts"]) >= 1
            assert len(data["tables"]["containers"]) >= 1

    async def test_create_backup_generates_metadata_file(self, backup_service_with_temp_dir, temp_backup_dir):
        """Test que le fichier metadata est créé."""
        service = backup_service_with_temp_dir

        metadata = await service.create_backup()

        meta_file = temp_backup_dir / f"backup_{metadata.id}.meta.json"
        assert meta_file.exists()

        with open(meta_file) as f:
            meta_data = json.load(f)
            assert meta_data["id"] == metadata.id
            assert meta_data["filename"] == metadata.filename


class TestBackupServiceList:
    """Tests pour le listing des backups."""

    async def test_list_backups_empty(self, backup_service_with_temp_dir):
        """Test listing sans backups."""
        service = backup_service_with_temp_dir

        backups = await service.list_backups()

        assert backups == []

    async def test_list_backups_with_data(self, backup_service_with_temp_dir):
        """Test listing avec backups."""
        import asyncio
        service = backup_service_with_temp_dir

        # Créer quelques backups avec un délai pour avoir des IDs différents
        await service.create_backup()
        await asyncio.sleep(1.1)  # Attendre pour avoir un timestamp différent
        await service.create_backup()

        backups = await service.list_backups()

        assert len(backups) == 2
        # Triés par date décroissante
        assert backups[0].created_at >= backups[1].created_at


class TestBackupServiceGet:
    """Tests pour la récupération d'un backup."""

    async def test_get_backup_exists(self, backup_service_with_temp_dir):
        """Test récupération backup existant."""
        service = backup_service_with_temp_dir

        created = await service.create_backup()
        retrieved = await service.get_backup(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.filename == created.filename

    async def test_get_backup_not_found(self, backup_service_with_temp_dir):
        """Test récupération backup inexistant."""
        service = backup_service_with_temp_dir

        result = await service.get_backup("nonexistent")

        assert result is None


class TestBackupServiceDelete:
    """Tests pour la suppression de backups."""

    async def test_delete_backup(self, backup_service_with_temp_dir, temp_backup_dir):
        """Test suppression backup."""
        service = backup_service_with_temp_dir

        created = await service.create_backup()
        backup_file = temp_backup_dir / created.filename
        meta_file = temp_backup_dir / f"backup_{created.id}.meta.json"

        assert backup_file.exists()
        assert meta_file.exists()

        result = await service.delete_backup(created.id)

        assert result is True
        assert not backup_file.exists()
        assert not meta_file.exists()

    async def test_delete_backup_not_found(self, backup_service_with_temp_dir):
        """Test suppression backup inexistant."""
        service = backup_service_with_temp_dir

        result = await service.delete_backup("nonexistent")

        assert result is False


class TestBackupServiceCleanup:
    """Tests pour le nettoyage des vieux backups."""

    async def test_cleanup_old_backups(self, backup_service_with_temp_dir, temp_backup_dir):
        """Test nettoyage des backups anciens."""
        import asyncio
        service = backup_service_with_temp_dir

        # Créer un backup "ancien" en modifiant la date
        old_backup = await service.create_backup()

        # Modifier la date dans les métadonnées pour le rendre ancien
        meta_file = temp_backup_dir / f"backup_{old_backup.id}.meta.json"
        with open(meta_file) as f:
            meta_data = json.load(f)

        old_date = (datetime.utcnow() - timedelta(days=60)).isoformat()
        meta_data["created_at"] = old_date
        with open(meta_file, 'w') as f:
            json.dump(meta_data, f)

        # Attendre pour avoir un timestamp différent
        await asyncio.sleep(1.1)

        # Créer un backup récent
        await service.create_backup()

        # Nettoyer avec rétention de 30 jours
        deleted = await service.cleanup_old_backups(retention_days=30)

        assert deleted == 1
        remaining = await service.list_backups()
        assert len(remaining) == 1


class TestBackupServiceGetFilePath:
    """Tests pour la récupération du chemin de fichier."""

    async def test_get_backup_file_path_exists(self, backup_service_with_temp_dir, temp_backup_dir):
        """Test récupération chemin fichier existant."""
        service = backup_service_with_temp_dir

        created = await service.create_backup()
        path = await service.get_backup_file_path(created.id)

        assert path is not None
        assert path.exists()
        assert path == temp_backup_dir / created.filename

    async def test_get_backup_file_path_not_found(self, backup_service_with_temp_dir):
        """Test récupération chemin fichier inexistant."""
        service = backup_service_with_temp_dir

        path = await service.get_backup_file_path("nonexistent")

        assert path is None


class TestBackupMetadata:
    """Tests pour BackupMetadata."""

    def test_backup_metadata_creation(self):
        """Test création BackupMetadata."""
        metadata = BackupMetadata(
            id="test-001",
            filename="backup_test-001.json.gz",
            created_at="2024-01-01T00:00:00",
            size_bytes=1024,
            tables={"hosts": 10, "containers": 20},
        )

        assert metadata.id == "test-001"
        assert metadata.version == "1.0"
        assert metadata.compressed is True
        assert metadata.tables["hosts"] == 10

    def test_backup_metadata_defaults(self):
        """Test valeurs par défaut BackupMetadata."""
        metadata = BackupMetadata(
            id="test-001",
            filename="backup.json.gz",
            created_at="2024-01-01T00:00:00",
            size_bytes=0,
            tables={},
        )

        assert metadata.version == "1.0"
        assert metadata.compressed is True
