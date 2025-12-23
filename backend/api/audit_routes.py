"""Routes API pour les logs d'audit (Admin only)."""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.auth_models import User, AuditActionType
from services.audit_service import AuditService
from api.dependencies import require_admin_or_bypass

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    user_id: Optional[str]
    username: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    details: dict
    success: bool
    error_message: Optional[str]

    class Config:
        from_attributes = True


class AuditLogsResponse(BaseModel):
    logs: List[AuditLogResponse]
    total: int
    skip: int
    limit: int


@router.get("/logs", response_model=AuditLogsResponse)
async def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    success: Optional[bool] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """
    Récupère les logs d'audit avec filtres (admin only).

    - **skip**: Nombre d'entrées à sauter (pagination)
    - **limit**: Nombre max d'entrées à retourner
    - **action**: Filtrer par type d'action
    - **user_id**: Filtrer par ID utilisateur
    - **success**: Filtrer par succès (true/false)
    - **from_date**: Date de début (ISO format)
    - **to_date**: Date de fin (ISO format)
    """
    audit_service = AuditService(db)

    # Convertir action string en enum si fourni
    action_enum = None
    if action:
        try:
            action_enum = AuditActionType(action)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Action invalide: {action}"
            )

    logs, total = await audit_service.get_logs(
        skip=skip,
        limit=limit,
        action=action_enum,
        user_id=user_id,
        success=success,
        from_date=from_date,
        to_date=to_date,
    )

    return AuditLogsResponse(
        logs=[
            AuditLogResponse(
                id=log.id,
                timestamp=log.timestamp,
                user_id=log.user_id,
                username=log.username,
                action=log.action.value,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                details=log.details or {},
                success=log.success,
                error_message=log.error_message,
            )
            for log in logs
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/users/{user_id}/activity", response_model=List[AuditLogResponse])
async def get_user_activity(
    user_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Récupère l'activité d'un utilisateur spécifique (admin only)."""
    audit_service = AuditService(db)

    logs = await audit_service.get_user_activity(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    return [
        AuditLogResponse(
            id=log.id,
            timestamp=log.timestamp,
            user_id=log.user_id,
            username=log.username,
            action=log.action.value,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            details=log.details or {},
            success=log.success,
            error_message=log.error_message,
        )
        for log in logs
    ]


@router.delete("/cleanup")
async def cleanup_old_logs(
    days: int = Query(None, description="Jours de rétention (défaut: config)"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """
    Supprime les logs plus anciens que N jours (admin only).

    Si days n'est pas spécifié, utilise la valeur de configuration.
    """
    audit_service = AuditService(db)
    count = await audit_service.cleanup_old_logs(days=days)

    return {"message": f"{count} log(s) supprimé(s)"}
