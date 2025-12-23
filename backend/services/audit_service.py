"""Service d'audit pour logger les actions de sécurité."""

from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_

from db.auth_models import AuditLog, AuditActionType
from config import get_settings

settings = get_settings()


class AuditService:
    """Service pour la gestion des logs d'audit."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: AuditActionType,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """
        Enregistre une action dans les logs d'audit.

        Args:
            action: Type d'action (login, logout, etc.)
            user_id: ID de l'utilisateur qui a fait l'action
            username: Nom d'utilisateur (conservé même si user supprimé)
            ip_address: Adresse IP du client
            user_agent: User-Agent du navigateur
            resource_type: Type de ressource affectée (user, session, etc.)
            resource_id: ID de la ressource affectée
            details: Détails additionnels en JSON
            success: L'action a-t-elle réussi?
            error_message: Message d'erreur si échec

        Returns:
            AuditLog créé
        """
        log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            success=success,
            error_message=error_message,
        )

        self.db.add(log)
        await self.db.flush()
        return log

    async def log_login(
        self,
        user_id: Optional[str],
        username: str,
        ip_address: Optional[str],
        user_agent: Optional[str],
        success: bool,
        error_message: Optional[str] = None,
    ) -> AuditLog:
        """Log une tentative de connexion."""
        action = AuditActionType.LOGIN if success else AuditActionType.LOGIN_FAILED
        return await self.log(
            action=action,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
        )

    async def log_logout(
        self,
        user_id: str,
        username: str,
        ip_address: Optional[str],
        session_id: Optional[str] = None,
    ) -> AuditLog:
        """Log une déconnexion."""
        return await self.log(
            action=AuditActionType.LOGOUT,
            user_id=user_id,
            username=username,
            ip_address=ip_address,
            resource_type="session" if session_id else None,
            resource_id=session_id,
            success=True,
        )

    async def get_logs(
        self,
        skip: int = 0,
        limit: int = 50,
        action: Optional[AuditActionType] = None,
        user_id: Optional[str] = None,
        success: Optional[bool] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> tuple[List[AuditLog], int]:
        """
        Récupère les logs d'audit avec filtres.

        Returns:
            Tuple (logs, total_count)
        """
        # Construire la requête de base
        conditions = []

        if action:
            conditions.append(AuditLog.action == action)
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        if success is not None:
            conditions.append(AuditLog.success == success)
        if from_date:
            conditions.append(AuditLog.timestamp >= from_date)
        if to_date:
            conditions.append(AuditLog.timestamp <= to_date)

        # Requête pour les résultats
        query = select(AuditLog)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(AuditLog.timestamp.desc())
        query = query.offset(skip).limit(limit)

        result = await self.db.execute(query)
        logs = result.scalars().all()

        # Requête pour le count total
        from sqlalchemy import func
        count_query = select(func.count(AuditLog.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        return list(logs), total

    async def get_user_activity(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> List[AuditLog]:
        """Récupère l'activité d'un utilisateur."""
        query = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def cleanup_old_logs(self, days: Optional[int] = None) -> int:
        """
        Supprime les logs plus anciens que N jours.

        Args:
            days: Nombre de jours de rétention (par défaut: config)

        Returns:
            Nombre de logs supprimés
        """
        retention_days = days or settings.audit_log_retention_days
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        # Compter d'abord
        from sqlalchemy import func
        count_query = select(func.count(AuditLog.id)).where(
            AuditLog.timestamp < cutoff
        )
        count_result = await self.db.execute(count_query)
        count = count_result.scalar() or 0

        # Supprimer
        stmt = delete(AuditLog).where(AuditLog.timestamp < cutoff)
        await self.db.execute(stmt)

        return count
