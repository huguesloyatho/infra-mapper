"""Routes d'authentification."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.database import get_db
from db.auth_models import User, IdentityProvider
from models.auth_schemas import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    ChangePasswordRequest,
    UserMeResponse,
    SessionResponse,
    AuthProvidersResponse,
    IdpPublicInfo,
    LoginResponse,
    Login2FARequest,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    TOTPDisableRequest,
)
from services.auth_service import AuthService
from services.user_service import UserService
from services.totp_service import TOTPService
from services.audit_service import AuditService, AuditActionType
from api.dependencies import get_current_user

logger = logging.getLogger(__name__)
settings = get_settings()

# Durée de validité du token temporaire 2FA (5 minutes)
TEMP_TOKEN_EXPIRE_MINUTES = 5

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extrait l'IP et le User-Agent de la requête."""
    # IP (gérer les proxys)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None

    user_agent = request.headers.get("User-Agent")

    return ip, user_agent


def create_temp_2fa_token(user_id: str) -> str:
    """Crée un token temporaire pour compléter le 2FA."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=TEMP_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "sub": user_id,
        "type": "2fa_temp",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def verify_temp_2fa_token(token: str) -> Optional[str]:
    """Vérifie un token temporaire 2FA et retourne le user_id."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "2fa_temp":
            return None
        return payload.get("sub")
    except JWTError:
        return None


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Authentifie un utilisateur local avec username/password.

    Si l'utilisateur a le 2FA activé, retourne requires_2fa=true avec un token temporaire.
    L'utilisateur doit ensuite appeler /login/2fa pour compléter l'authentification.

    Returns:
        LoginResponse avec tokens ou demande de 2FA
    """
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="L'authentification est désactivée"
        )

    ip_address, user_agent = get_client_info(request)
    audit_service = AuditService(db)

    # Première étape: vérifier username/password
    auth_service = AuthService(db)
    user_service = UserService(db)

    # Chercher l'utilisateur
    user = await user_service.get_user_by_username(data.username)
    if not user:
        user = await user_service.get_user_by_email(data.username)

    if not user:
        await audit_service.log(
            action=AuditActionType.LOGIN_FAILED,
            ip_address=ip_address,
            details={"username": data.username, "reason": "user_not_found"},
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Vérifier si le compte est actif
    if not user.is_active:
        await audit_service.log(
            action=AuditActionType.LOGIN_FAILED,
            user_id=user.id,
            ip_address=ip_address,
            details={"reason": "account_disabled"},
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Compte désactivé",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Vérifier le verrouillage
    if user.is_locked:
        if user.locked_until and user.locked_until > datetime.utcnow():
            remaining = (user.locked_until - datetime.utcnow()).seconds // 60
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Compte verrouillé. Réessayez dans {remaining} minutes",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            # Déverrouiller automatiquement
            user.is_locked = False
            user.failed_login_attempts = 0
            user.locked_until = None
            await db.commit()

    # Vérifier que c'est un utilisateur local
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur SSO, utilisez la connexion SSO",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Vérifier le mot de passe
    if not auth_service.verify_password(data.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.is_locked = True
            user.locked_until = datetime.utcnow() + timedelta(minutes=settings.lockout_duration_minutes)
            logger.warning(f"User {user.username} locked after {user.failed_login_attempts} failed attempts")
        await db.commit()

        await audit_service.log(
            action=AuditActionType.LOGIN_FAILED,
            user_id=user.id,
            ip_address=ip_address,
            details={"reason": "invalid_password"},
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Mot de passe correct - vérifier si 2FA activé
    if user.totp_enabled and user.totp_secret:
        # 2FA requis - retourner un token temporaire
        temp_token = create_temp_2fa_token(user.id)
        logger.info(f"2FA required for user: {user.username} from {ip_address}")

        return LoginResponse(
            requires_2fa=True,
            temp_token=temp_token,
        )

    # Pas de 2FA - créer la session et les tokens directement
    user.failed_login_attempts = 0
    user.last_login = datetime.utcnow()
    await db.commit()

    session, refresh_token = await auth_service.create_session(user, ip_address, user_agent)
    access_token = auth_service.create_access_token(user.id, session.id, user.role.value)

    await audit_service.log(
        action=AuditActionType.LOGIN,
        user_id=user.id,
        ip_address=ip_address,
        details={"method": "local"},
        success=True,
    )

    logger.info(f"User logged in: {user.username} from {ip_address}")

    return LoginResponse(
        requires_2fa=False,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60
    )


@router.post("/login/2fa", response_model=TokenResponse)
async def login_2fa(
    data: Login2FARequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Complète l'authentification avec un code TOTP ou code de secours.

    Requis après un login qui retourne requires_2fa=true.

    Returns:
        Tokens d'accès et de rafraîchissement
    """
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="L'authentification est désactivée"
        )

    ip_address, user_agent = get_client_info(request)
    audit_service = AuditService(db)

    # Vérifier le token temporaire
    user_id = verify_temp_2fa_token(data.temp_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token temporaire invalide ou expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Récupérer l'utilisateur
    user_service = UserService(db)
    user = await user_service.get_user(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA non activé pour cet utilisateur",
        )

    # Vérifier le code TOTP
    totp_service = TOTPService()
    code_valid = totp_service.verify_code(user.totp_secret, data.code)

    # Si le code TOTP n'est pas valide, vérifier les codes de secours
    backup_code_index = None
    if not code_valid and user.totp_backup_codes:
        code_valid, backup_code_index = totp_service.verify_backup_code(
            data.code, user.totp_backup_codes
        )

    if not code_valid:
        await audit_service.log(
            action=AuditActionType.TOTP_FAILED,
            user_id=user.id,
            ip_address=ip_address,
            details={"reason": "invalid_code"},
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Code 2FA invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Si un code de secours a été utilisé, le retirer
    if backup_code_index is not None:
        backup_codes = user.totp_backup_codes.copy()
        backup_codes.pop(backup_code_index)
        user.totp_backup_codes = backup_codes
        logger.info(f"Backup code used for user {user.username}, {len(backup_codes)} remaining")

    # Créer la session et les tokens
    auth_service = AuthService(db)
    user.failed_login_attempts = 0
    user.last_login = datetime.utcnow()
    await db.commit()

    session, refresh_token = await auth_service.create_session(user, ip_address, user_agent)
    access_token = auth_service.create_access_token(user.id, session.id, user.role.value)

    await audit_service.log(
        action=AuditActionType.LOGIN,
        user_id=user.id,
        ip_address=ip_address,
        details={"method": "local", "2fa": True, "backup_code": backup_code_index is not None},
        success=True,
    )

    logger.info(f"User logged in with 2FA: {user.username} from {ip_address}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Rafraîchit un access token.

    Returns:
        Nouveaux tokens d'accès et de rafraîchissement
    """
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="L'authentification est désactivée"
        )

    auth_service = AuthService(db)
    new_access, new_refresh, error = await auth_service.refresh_access_token(
        refresh_token=data.refresh_token
    )

    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.access_token_expire_minutes * 60
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Déconnecte l'utilisateur (révoque la session courante).
    """
    # Récupérer le token pour extraire le session_id
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")

    auth_service = AuthService(db)
    payload = auth_service.verify_token(token)

    if payload and payload.get("session_id"):
        await auth_service.revoke_session(payload["session_id"])
        logger.info(f"User logged out: {current_user.username}")

    return {"message": "Déconnexion réussie"}


@router.post("/logout-all")
async def logout_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Déconnecte l'utilisateur de toutes ses sessions.
    """
    auth_service = AuthService(db)
    count = await auth_service.revoke_all_sessions(current_user.id)

    logger.info(f"User logged out from all sessions: {current_user.username} ({count} sessions)")

    return {"message": f"{count} session(s) révoquée(s)"}


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Récupère les informations de l'utilisateur connecté.
    """
    user_service = UserService(db)
    sessions = await user_service.get_user_sessions(current_user.id)

    # Récupérer le nom de l'IdP si SSO
    idp_name = None
    if current_user.idp_id:
        result = await db.execute(
            select(IdentityProvider.display_name).where(
                IdentityProvider.id == current_user.idp_id
            )
        )
        idp_name = result.scalar_one_or_none()

    return UserMeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        display_name=current_user.display_name,
        role=current_user.role.value,
        is_active=current_user.is_active,
        is_locked=current_user.is_locked,
        is_sso=current_user.idp_id is not None,
        idp_name=idp_name,
        last_login=current_user.last_login,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        sessions_count=len(sessions),
        totp_enabled=current_user.totp_enabled,
    )


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change le mot de passe de l'utilisateur connecté.
    """
    user_service = UserService(db)
    success, error = await user_service.change_password(
        user_id=current_user.id,
        current_password=data.current_password,
        new_password=data.new_password
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )

    logger.info(f"Password changed for user: {current_user.username}")

    return {"message": "Mot de passe modifié avec succès"}


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Liste les sessions actives de l'utilisateur connecté.
    """
    # Récupérer le session_id courant
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")

    auth_service = AuthService(db)
    payload = auth_service.verify_token(token)
    current_session_id = payload.get("session_id") if payload else None

    user_service = UserService(db)
    sessions = await user_service.get_user_sessions(current_user.id)

    return [
        SessionResponse(
            id=s.id,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            is_current=s.id == current_session_id,
            created_at=s.created_at,
            last_used_at=s.last_used_at,
            expires_at=s.expires_at,
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Révoque une session spécifique de l'utilisateur connecté.
    """
    # Vérifier que la session appartient à l'utilisateur
    user_service = UserService(db)
    sessions = await user_service.get_user_sessions(current_user.id)

    session_ids = [s.id for s in sessions]
    if session_id not in session_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session non trouvée"
        )

    auth_service = AuthService(db)
    await auth_service.revoke_session(session_id)

    logger.info(f"Session revoked for user {current_user.username}: {session_id}")

    return {"message": "Session révoquée"}


# === 2FA / TOTP Endpoints ===

@router.post("/2fa/setup", response_model=TOTPSetupResponse)
async def setup_2fa(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Initialise la configuration 2FA pour l'utilisateur.

    Génère un secret TOTP, un QR code et des codes de secours.
    L'utilisateur doit ensuite appeler /2fa/enable avec un code valide pour activer le 2FA.

    Note: Ne peut pas être utilisé par les utilisateurs SSO.
    """
    ip_address, _ = get_client_info(request)
    audit_service = AuditService(db)

    # Vérifier que ce n'est pas un utilisateur SSO
    if current_user.idp_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le 2FA local n'est pas disponible pour les utilisateurs SSO"
        )

    # Vérifier que le 2FA n'est pas déjà activé
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le 2FA est déjà activé. Désactivez-le d'abord pour le reconfigurer."
        )

    # Générer le secret et le QR code
    totp_service = TOTPService()
    secret = totp_service.generate_secret()
    qr_code = totp_service.generate_qr_code(secret, current_user.username, current_user.email)

    # Générer les codes de secours
    plain_codes, hashed_codes = totp_service.generate_backup_codes()

    # Sauvegarder le secret et les codes (mais pas encore activé)
    current_user.totp_secret = secret
    current_user.totp_backup_codes = hashed_codes
    current_user.totp_enabled = False  # Sera activé après vérification
    await db.commit()

    await audit_service.log(
        action=AuditActionType.TOTP_SETUP,
        user_id=current_user.id,
        ip_address=ip_address,
        details={"step": "setup_initiated"},
        success=True,
    )

    logger.info(f"2FA setup initiated for user: {current_user.username}")

    return TOTPSetupResponse(
        secret=secret,
        qr_code=qr_code,
        backup_codes=plain_codes
    )


@router.post("/2fa/enable")
async def enable_2fa(
    data: TOTPVerifyRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Active le 2FA après vérification d'un code TOTP valide.

    Doit être appelé après /2fa/setup avec un code généré par l'app authenticator.
    """
    ip_address, _ = get_client_info(request)
    audit_service = AuditService(db)

    # Vérifier que le setup a été fait
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Veuillez d'abord configurer le 2FA avec /2fa/setup"
        )

    # Vérifier que le 2FA n'est pas déjà activé
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le 2FA est déjà activé"
        )

    # Vérifier le code TOTP
    totp_service = TOTPService()
    if not totp_service.verify_code(current_user.totp_secret, data.code):
        await audit_service.log(
            action=AuditActionType.TOTP_ENABLED,
            user_id=current_user.id,
            ip_address=ip_address,
            details={"reason": "invalid_code"},
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code TOTP invalide. Vérifiez que l'heure de votre appareil est synchronisée."
        )

    # Activer le 2FA
    current_user.totp_enabled = True
    await db.commit()

    await audit_service.log(
        action=AuditActionType.TOTP_ENABLED,
        user_id=current_user.id,
        ip_address=ip_address,
        details={},
        success=True,
    )

    logger.info(f"2FA enabled for user: {current_user.username}")

    return {"message": "2FA activé avec succès"}


@router.post("/2fa/disable")
async def disable_2fa(
    data: TOTPDisableRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Désactive le 2FA.

    Requiert le mot de passe pour confirmation.
    """
    ip_address, _ = get_client_info(request)
    audit_service = AuditService(db)

    # Vérifier que le 2FA est activé
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le 2FA n'est pas activé"
        )

    # Vérifier que ce n'est pas un utilisateur SSO
    if current_user.idp_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Opération non disponible pour les utilisateurs SSO"
        )

    # Vérifier le mot de passe
    auth_service = AuthService(db)
    if not auth_service.verify_password(data.password, current_user.password_hash):
        await audit_service.log(
            action=AuditActionType.TOTP_DISABLED,
            user_id=current_user.id,
            ip_address=ip_address,
            details={"reason": "invalid_password"},
            success=False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mot de passe incorrect"
        )

    # Désactiver le 2FA
    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.totp_backup_codes = None
    await db.commit()

    await audit_service.log(
        action=AuditActionType.TOTP_DISABLED,
        user_id=current_user.id,
        ip_address=ip_address,
        details={},
        success=True,
    )

    logger.info(f"2FA disabled for user: {current_user.username}")

    return {"message": "2FA désactivé"}


@router.post("/2fa/regenerate-backup-codes")
async def regenerate_backup_codes(
    data: TOTPVerifyRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Régénère les codes de secours.

    Requiert un code TOTP valide pour confirmation.
    Les anciens codes de secours sont invalidés.
    """
    ip_address, _ = get_client_info(request)
    audit_service = AuditService(db)

    # Vérifier que le 2FA est activé
    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le 2FA n'est pas activé"
        )

    # Vérifier le code TOTP
    totp_service = TOTPService()
    if not totp_service.verify_code(current_user.totp_secret, data.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code TOTP invalide"
        )

    # Générer de nouveaux codes de secours
    plain_codes, hashed_codes = totp_service.generate_backup_codes()
    current_user.totp_backup_codes = hashed_codes
    await db.commit()

    await audit_service.log(
        action=AuditActionType.TOTP_SETUP,
        user_id=current_user.id,
        ip_address=ip_address,
        details={"action": "regenerate_backup_codes"},
        success=True,
    )

    logger.info(f"Backup codes regenerated for user: {current_user.username}")

    return {"backup_codes": plain_codes}


@router.get("/providers", response_model=AuthProvidersResponse)
async def list_providers(
    db: AsyncSession = Depends(get_db)
):
    """
    Liste les fournisseurs d'authentification disponibles (public).

    Utilisé par la page de login pour afficher les options.
    """
    if not settings.auth_enabled:
        return AuthProvidersResponse(
            local_enabled=False,
            providers=[]
        )

    # Récupérer les IdP activés
    result = await db.execute(
        select(IdentityProvider).where(IdentityProvider.is_enabled == True)
    )
    idps = result.scalars().all()

    providers = [
        IdpPublicInfo(
            id=idp.id,
            name=idp.name,
            display_name=idp.display_name,
            provider_type=idp.provider_type.value
        )
        for idp in idps
    ]

    return AuthProvidersResponse(
        local_enabled=True,
        providers=providers
    )
