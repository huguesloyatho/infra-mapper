"""Routes API pour le système de backup."""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from db import get_db
from services.backup_service import BackupService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/backups", tags=["backups"])


# =============================================================================
# Schemas
# =============================================================================

class BackupCreate(BaseModel):
    """Paramètres de création d'un backup."""
    include_logs: bool = Field(default=False, description="Inclure les logs des containers")


class BackupRestore(BaseModel):
    """Paramètres de restauration."""
    tables: Optional[List[str]] = Field(default=None, description="Tables à restaurer (null = toutes)")
    clear_existing: bool = Field(default=True, description="Supprimer les données existantes")


class BackupResponse(BaseModel):
    """Réponse avec métadonnées d'un backup."""
    id: str
    filename: str
    created_at: str
    size_bytes: int
    size_human: str
    tables: dict


class BackupCleanup(BaseModel):
    """Paramètres de nettoyage."""
    retention_days: int = Field(default=30, ge=1, le=365)


# =============================================================================
# Helpers
# =============================================================================

def format_size(size_bytes: int) -> str:
    """Formate une taille en bytes en format lisible."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def metadata_to_response(meta) -> BackupResponse:
    """Convertit les métadonnées en réponse API."""
    return BackupResponse(
        id=meta.id,
        filename=meta.filename,
        created_at=meta.created_at,
        size_bytes=meta.size_bytes,
        size_human=format_size(meta.size_bytes),
        tables=meta.tables,
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.get("", response_model=List[BackupResponse])
async def list_backups(db: AsyncSession = Depends(get_db)):
    """Liste tous les backups disponibles."""
    service = BackupService(db)
    backups = await service.list_backups()
    return [metadata_to_response(b) for b in backups]


@router.post("", response_model=BackupResponse)
async def create_backup(
    data: BackupCreate = BackupCreate(),
    db: AsyncSession = Depends(get_db),
):
    """Crée un nouveau backup."""
    service = BackupService(db)
    metadata = await service.create_backup(include_logs=data.include_logs)
    return metadata_to_response(metadata)


@router.get("/{backup_id}", response_model=BackupResponse)
async def get_backup(backup_id: str, db: AsyncSession = Depends(get_db)):
    """Récupère les informations d'un backup."""
    service = BackupService(db)
    metadata = await service.get_backup(backup_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Backup non trouvé")
    return metadata_to_response(metadata)


@router.get("/{backup_id}/download")
async def download_backup(backup_id: str, db: AsyncSession = Depends(get_db)):
    """Télécharge un fichier backup."""
    service = BackupService(db)
    filepath = await service.get_backup_file_path(backup_id)
    if not filepath:
        raise HTTPException(status_code=404, detail="Backup non trouvé")

    return FileResponse(
        path=str(filepath),
        filename=filepath.name,
        media_type="application/gzip",
    )


@router.post("/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    data: BackupRestore = BackupRestore(),
    db: AsyncSession = Depends(get_db),
):
    """Restaure un backup."""
    service = BackupService(db)

    # Vérifier que le backup existe
    metadata = await service.get_backup(backup_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="Backup non trouvé")

    try:
        stats = await service.restore_backup(
            backup_id=backup_id,
            tables=data.tables,
            clear_existing=data.clear_existing,
        )
        return {
            "success": True,
            "backup_id": backup_id,
            "restored": stats["restored"],
            "errors": stats["errors"],
        }
    except Exception as e:
        logger.error(f"Erreur restauration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{backup_id}")
async def delete_backup(backup_id: str, db: AsyncSession = Depends(get_db)):
    """Supprime un backup."""
    service = BackupService(db)
    if not await service.delete_backup(backup_id):
        raise HTTPException(status_code=404, detail="Backup non trouvé")
    return {"status": "deleted", "backup_id": backup_id}


@router.post("/cleanup")
async def cleanup_old_backups(
    data: BackupCleanup = BackupCleanup(),
    db: AsyncSession = Depends(get_db),
):
    """Supprime les backups plus anciens que retention_days."""
    service = BackupService(db)
    deleted = await service.cleanup_old_backups(data.retention_days)
    return {
        "deleted_count": deleted,
        "retention_days": data.retention_days,
    }
