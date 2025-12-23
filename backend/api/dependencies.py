"""Dépendances FastAPI pour l'authentification et l'autorisation."""

from typing import Optional, List

from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.database import get_db
from db.auth_models import User, RoleEnum
from services.auth_service import AuthService
from services.user_service import UserService

settings = get_settings()

# Security scheme pour Swagger UI
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Extrait et valide l'utilisateur depuis le token JWT.

    Raises:
        HTTPException 401 si non authentifié ou token invalide
    """
    # Si l'auth est désactivée, lever une erreur (cette dépendance ne devrait pas être appelée)
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Authentication is disabled"
        )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Non authentifié",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = AuthService(db)
    payload = auth_service.verify_token(credentials.credentials)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Vérifier que c'est un access token
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Vérifier la session
    session_id = payload.get("session_id")
    if session_id:
        session = await auth_service.validate_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expirée ou révoquée",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Récupérer l'utilisateur
    user_id = payload.get("sub")
    user_service = UserService(db)
    user = await user_service.get_user(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouvé",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Compte désactivé",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Récupère l'utilisateur courant si authentifié, None sinon.

    Utile pour les endpoints qui fonctionnent avec ou sans auth.
    """
    if not settings.auth_enabled:
        return None

    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


def require_role(required_roles: List[RoleEnum]):
    """
    Factory de dépendance pour vérifier les rôles.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: User = Depends(require_admin)):
            ...
    """
    async def check_role(
        current_user: User = Depends(get_current_user)
    ) -> User:
        if current_user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle insuffisant. Requis: {[r.value for r in required_roles]}"
            )
        return current_user

    return check_role


# Dépendances pré-configurées pour chaque niveau de rôle
require_super_admin = require_role([RoleEnum.SUPER_ADMIN])
require_admin = require_role([RoleEnum.SUPER_ADMIN, RoleEnum.ADMIN])
require_operator = require_role([RoleEnum.SUPER_ADMIN, RoleEnum.ADMIN, RoleEnum.OPERATOR])
require_viewer = require_role([RoleEnum.SUPER_ADMIN, RoleEnum.ADMIN, RoleEnum.OPERATOR, RoleEnum.VIEWER])


async def require_auth_or_bypass(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Vérifie l'authentification si AUTH_ENABLED=true, sinon bypass.

    Utilisé pour les endpoints qui doivent être protégés quand l'auth est activée,
    mais accessibles sans auth quand elle est désactivée.
    """
    if not settings.auth_enabled:
        return None

    return await get_current_user(credentials, db)


async def require_admin_or_bypass(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Vérifie l'admin si AUTH_ENABLED=true, sinon bypass.
    """
    if not settings.auth_enabled:
        return None

    user = await get_current_user(credentials, db)
    if user.role not in [RoleEnum.SUPER_ADMIN, RoleEnum.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs"
        )
    return user


# === Agent API Key Authentication (existant, conservé) ===

async def verify_agent_api_key(authorization: str = Header(...)) -> bool:
    """
    Vérifie la clé API des agents.

    Cette authentification est séparée de l'auth utilisateur et reste
    inchangée pour la compatibilité avec les agents existants.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Format d'autorisation invalide"
        )

    token = authorization.replace("Bearer ", "")
    if token != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API invalide"
        )

    return True
