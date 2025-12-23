"""Service de backup et restauration de la base de données."""

import logging
import os
import json
import gzip
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, asdict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Host, Container, Network, Connection, ContainerLog, Vm,
    AlertChannel, AlertRule, Alert,
    User, IdentityProvider, AuditLog
)

logger = logging.getLogger(__name__)


@dataclass
class BackupMetadata:
    """Métadonnées d'un backup."""
    id: str
    filename: str
    created_at: str
    size_bytes: int
    tables: dict  # {table_name: row_count}
    version: str = "1.0"
    compressed: bool = True


class BackupService:
    """Service de backup et restauration."""

    BACKUP_DIR = Path("/app/backups")
    TABLES_TO_BACKUP = [
        ("hosts", Host),
        ("containers", Container),
        ("networks", Network),
        ("connections", Connection),
        ("vms", Vm),
        ("alert_channels", AlertChannel),
        ("alert_rules", AlertRule),
        ("alerts", Alert),
        ("users", User),
        ("identity_providers", IdentityProvider),
    ]

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    async def create_backup(self, include_logs: bool = False) -> BackupMetadata:
        """
        Crée un backup complet de la base de données.

        Args:
            include_logs: Inclure les logs des containers (peut être volumineux)

        Returns:
            Métadonnées du backup créé
        """
        backup_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{backup_id}.json.gz"
        filepath = self.BACKUP_DIR / filename

        logger.info(f"Création du backup {backup_id}...")

        backup_data = {
            "metadata": {
                "version": "1.0",
                "created_at": datetime.utcnow().isoformat(),
                "include_logs": include_logs,
            },
            "tables": {}
        }

        tables_count = {}

        # Exporter chaque table
        tables = list(self.TABLES_TO_BACKUP)
        if include_logs:
            tables.append(("container_logs", ContainerLog))

        for table_name, model in tables:
            try:
                result = await self.db.execute(select(model))
                rows = result.scalars().all()

                # Convertir en dict
                table_data = []
                for row in rows:
                    row_dict = {}
                    for column in row.__table__.columns:
                        value = getattr(row, column.name)
                        # Convertir les types non-JSON
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        elif hasattr(value, 'value'):  # Enum
                            value = value.value
                        row_dict[column.name] = value
                    table_data.append(row_dict)

                backup_data["tables"][table_name] = table_data
                tables_count[table_name] = len(table_data)
                logger.info(f"  - {table_name}: {len(table_data)} lignes")

            except Exception as e:
                logger.error(f"Erreur export {table_name}: {e}")
                tables_count[table_name] = 0

        # Compresser et sauvegarder
        json_str = json.dumps(backup_data, ensure_ascii=False, indent=None)
        with gzip.open(filepath, 'wt', encoding='utf-8') as f:
            f.write(json_str)

        size_bytes = filepath.stat().st_size

        metadata = BackupMetadata(
            id=backup_id,
            filename=filename,
            created_at=datetime.utcnow().isoformat(),
            size_bytes=size_bytes,
            tables=tables_count,
        )

        # Sauvegarder les métadonnées
        meta_path = self.BACKUP_DIR / f"backup_{backup_id}.meta.json"
        with open(meta_path, 'w') as f:
            json.dump(asdict(metadata), f)

        logger.info(f"Backup {backup_id} créé: {size_bytes} bytes")
        return metadata

    async def list_backups(self) -> List[BackupMetadata]:
        """Liste tous les backups disponibles."""
        backups = []

        for meta_file in self.BACKUP_DIR.glob("*.meta.json"):
            try:
                with open(meta_file) as f:
                    data = json.load(f)
                    backups.append(BackupMetadata(**data))
            except Exception as e:
                logger.warning(f"Erreur lecture {meta_file}: {e}")

        # Trier par date décroissante
        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups

    async def get_backup(self, backup_id: str) -> Optional[BackupMetadata]:
        """Récupère les métadonnées d'un backup."""
        meta_path = self.BACKUP_DIR / f"backup_{backup_id}.meta.json"
        if not meta_path.exists():
            return None

        with open(meta_path) as f:
            data = json.load(f)
            return BackupMetadata(**data)

    async def delete_backup(self, backup_id: str) -> bool:
        """Supprime un backup."""
        meta_path = self.BACKUP_DIR / f"backup_{backup_id}.meta.json"
        data_path = self.BACKUP_DIR / f"backup_{backup_id}.json.gz"

        deleted = False
        if meta_path.exists():
            meta_path.unlink()
            deleted = True
        if data_path.exists():
            data_path.unlink()
            deleted = True

        if deleted:
            logger.info(f"Backup {backup_id} supprimé")
        return deleted

    async def restore_backup(
        self,
        backup_id: str,
        tables: Optional[List[str]] = None,
        clear_existing: bool = True
    ) -> dict:
        """
        Restaure un backup.

        Args:
            backup_id: ID du backup à restaurer
            tables: Liste des tables à restaurer (None = toutes)
            clear_existing: Supprimer les données existantes avant restauration

        Returns:
            Statistiques de restauration
        """
        filepath = self.BACKUP_DIR / f"backup_{backup_id}.json.gz"
        if not filepath.exists():
            raise FileNotFoundError(f"Backup {backup_id} non trouvé")

        logger.info(f"Restauration du backup {backup_id}...")

        # Charger le backup
        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            backup_data = json.load(f)

        stats = {"restored": {}, "errors": []}

        # Mapper les noms de tables vers les modèles
        table_models = {name: model for name, model in self.TABLES_TO_BACKUP}
        table_models["container_logs"] = ContainerLog

        # Restaurer chaque table
        tables_to_restore = tables or list(backup_data["tables"].keys())

        # Ordre de restauration (pour respecter les FK)
        restore_order = [
            "users", "identity_providers",
            "hosts", "vms",
            "containers", "networks", "connections",
            "alert_channels", "alert_rules", "alerts",
            "container_logs"
        ]

        for table_name in restore_order:
            if table_name not in tables_to_restore:
                continue
            if table_name not in backup_data["tables"]:
                continue

            model = table_models.get(table_name)
            if not model:
                continue

            try:
                rows = backup_data["tables"][table_name]

                if clear_existing:
                    # Supprimer les données existantes
                    await self.db.execute(text(f"DELETE FROM {table_name}"))

                # Insérer les nouvelles données
                for row_data in rows:
                    # Convertir les dates ISO en datetime
                    for key, value in row_data.items():
                        if isinstance(value, str) and 'T' in value:
                            try:
                                row_data[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            except ValueError:
                                pass

                    obj = model(**row_data)
                    self.db.add(obj)

                await self.db.flush()
                stats["restored"][table_name] = len(rows)
                logger.info(f"  - {table_name}: {len(rows)} lignes restaurées")

            except Exception as e:
                logger.error(f"Erreur restauration {table_name}: {e}")
                stats["errors"].append(f"{table_name}: {str(e)}")
                await self.db.rollback()

        await self.db.commit()
        logger.info(f"Restauration terminée: {stats}")
        return stats

    async def cleanup_old_backups(self, retention_days: int = 30) -> int:
        """
        Supprime les backups plus anciens que retention_days.

        Returns:
            Nombre de backups supprimés
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        deleted = 0

        backups = await self.list_backups()
        for backup in backups:
            backup_date = datetime.fromisoformat(backup.created_at.replace('Z', '+00:00'))
            if backup_date < cutoff:
                if await self.delete_backup(backup.id):
                    deleted += 1

        logger.info(f"Nettoyage: {deleted} backups supprimés (rétention: {retention_days} jours)")
        return deleted

    async def get_backup_file_path(self, backup_id: str) -> Optional[Path]:
        """Retourne le chemin du fichier backup pour téléchargement."""
        filepath = self.BACKUP_DIR / f"backup_{backup_id}.json.gz"
        if filepath.exists():
            return filepath
        return None


class ScheduledBackupService:
    """Service de backup planifié."""

    def __init__(self, db_session_factory):
        """Initialise le service."""
        self.db_session_factory = db_session_factory
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(
        self,
        interval_hours: int = 24,
        retention_days: int = 30,
        include_logs: bool = False
    ):
        """Démarre les backups automatiques."""
        self._running = True
        logger.info(f"Backups automatiques activés: toutes les {interval_hours}h, rétention {retention_days}j")

        while self._running:
            try:
                async with self.db_session_factory() as db:
                    service = BackupService(db)

                    # Créer un backup
                    await service.create_backup(include_logs=include_logs)

                    # Nettoyer les anciens
                    await service.cleanup_old_backups(retention_days)

            except Exception as e:
                logger.error(f"Erreur backup automatique: {e}")

            # Attendre le prochain intervalle
            await asyncio.sleep(interval_hours * 3600)

    def stop(self):
        """Arrête les backups automatiques."""
        self._running = False
        if self._task:
            self._task.cancel()
