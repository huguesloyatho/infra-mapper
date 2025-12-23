"""Routes API pour la gestion des utilisateurs (Admin only)."""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.auth_models import User, RoleEnum
from services.user_service import UserService
from services.audit_service import AuditService, AuditActionType
from api.dependencies import require_admin_or_bypass, get_current_user
from models.auth_schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    PasswordReset,
    RoleChange,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def user_to_response(user: User) -> UserResponse:
    """Convertit un modèle User en UserResponse."""
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        is_active=user.is_active,
        is_locked=user.is_locked,
        is_sso=user.idp_id is not None,
        idp_name=None,  # TODO: charger le nom de l'IdP si nécessaire
        last_login=user.last_login,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Liste tous les utilisateurs (admin only)."""
    user_service = UserService(db)

    role_filter = None
    if role:
        try:
            role_filter = RoleEnum(role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rôle invalide: {role}"
            )

    users, total = await user_service.list_users(
        skip=skip,
        limit=limit,
        role=role_filter,
        is_active=is_active
    )

    # Transformer en response
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "display_name": u.display_name,
            "role": u.role.value if hasattr(u.role, 'value') else u.role,
            "is_active": u.is_active,
            "is_locked": u.is_locked,
            "is_sso": u.idp_id is not None,
            "idp_name": None,
            "totp_enabled": u.totp_enabled or False,
            "last_login": u.last_login,
            "created_at": u.created_at,
            "updated_at": u.updated_at,
        }
        for u in users
    ]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Crée un nouvel utilisateur (admin only)."""
    user_service = UserService(db)
    audit_service = AuditService(db)

    # Vérifier que le username n'existe pas
    existing = await user_service.get_user_by_username(data.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom d'utilisateur existe déjà"
        )

    # Vérifier que l'email n'existe pas
    existing = await user_service.get_user_by_email(data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cet email existe déjà"
        )

    try:
        role = RoleEnum(data.role) if data.role else RoleEnum.VIEWER
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rôle invalide: {data.role}"
        )

    user = await user_service.create_user(
        username=data.username,
        email=data.email,
        password=data.password,
        role=role,
        display_name=data.display_name,
    )

    # Log audit
    await audit_service.log(
        action=AuditActionType.USER_CREATE,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"created_user_id": user.id, "username": user.username},
        success=True,
    )

    return user_to_response(user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Récupère un utilisateur par ID (admin only)."""
    user_service = UserService(db)
    user = await user_service.get_user(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    return user_to_response(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Met à jour un utilisateur (admin only)."""
    user_service = UserService(db)
    audit_service = AuditService(db)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    # Vérifier l'unicité de l'email si changé
    if data.email and data.email != user.email:
        existing = await user_service.get_user_by_email(data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cet email existe déjà"
            )

    updated = await user_service.update_user(
        user_id=user_id,
        email=data.email,
        display_name=data.display_name,
        is_active=data.is_active,
    )

    # Log audit
    await audit_service.log(
        action=AuditActionType.USER_UPDATE,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"updated_user_id": user_id},
        success=True,
    )

    return updated


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Supprime un utilisateur (admin only)."""
    user_service = UserService(db)
    audit_service = AuditService(db)

    # Empêcher l'auto-suppression
    if current_user and current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas supprimer votre propre compte"
        )

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    await user_service.delete_user(user_id)

    # Log audit
    await audit_service.log(
        action=AuditActionType.USER_DELETE,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"deleted_user_id": user_id, "username": user.username},
        success=True,
    )


@router.put("/{user_id}/role", response_model=UserResponse)
async def change_user_role(
    user_id: str,
    data: RoleChange,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Change le rôle d'un utilisateur (admin only)."""
    user_service = UserService(db)
    audit_service = AuditService(db)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    try:
        new_role = RoleEnum(data.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rôle invalide: {data.role}"
        )

    old_role = user.role
    updated = await user_service.change_role(user_id, new_role)

    # Log audit
    await audit_service.log(
        action=AuditActionType.ROLE_CHANGE,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={
            "target_user_id": user_id,
            "old_role": old_role.value,
            "new_role": new_role.value
        },
        success=True,
    )

    return updated


@router.post("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Active un utilisateur (admin only)."""
    user_service = UserService(db)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    return await user_service.update_user(user_id, is_active=True)


@router.post("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Désactive un utilisateur (admin only)."""
    user_service = UserService(db)

    # Empêcher l'auto-désactivation
    if current_user and current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas désactiver votre propre compte"
        )

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    return await user_service.update_user(user_id, is_active=False)


@router.post("/{user_id}/unlock", response_model=UserResponse)
async def unlock_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Déverrouille un utilisateur (admin only)."""
    user_service = UserService(db)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    return await user_service.unlock_user(user_id)


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    data: PasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Réinitialise le mot de passe d'un utilisateur (admin only)."""
    user_service = UserService(db)
    audit_service = AuditService(db)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    success, message = await user_service.reset_password(user_id, data.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )

    # Log audit
    await audit_service.log(
        action=AuditActionType.PASSWORD_CHANGE,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"target_user_id": user_id, "reset_by_admin": True},
        success=True,
    )

    return {"message": "Mot de passe réinitialisé"}


@router.delete("/{user_id}/sessions")
async def revoke_all_user_sessions(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Révoque toutes les sessions d'un utilisateur (admin only)."""
    from services.auth_service import AuthService

    user_service = UserService(db)
    auth_service = AuthService(db)
    audit_service = AuditService(db)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    count = await auth_service.logout_all_sessions(user_id)

    # Log audit
    await audit_service.log(
        action=AuditActionType.SESSION_REVOKE,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"target_user_id": user_id, "sessions_revoked": count},
        success=True,
    )

    return {"message": f"{count} session(s) révoquée(s)"}


@router.post("/{user_id}/reset-2fa")
async def reset_user_2fa(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Désactive le 2FA d'un utilisateur (admin only)."""
    user_service = UserService(db)
    audit_service = AuditService(db)

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur non trouvé"
        )

    if not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le 2FA n'est pas activé pour cet utilisateur"
        )

    # Désactiver le 2FA
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_backup_codes = None
    await db.commit()

    # Log audit
    await audit_service.log(
        action=AuditActionType.TOTP_DISABLE,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"target_user_id": str(user_id), "reset_by_admin": True},
        success=True,
    )

    return {"message": "2FA désactivé pour l'utilisateur"}
