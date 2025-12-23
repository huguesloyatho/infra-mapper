"""Service d'authentification pour la gestion des utilisateurs et sessions."""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.auth_models import User, UserSession, RoleEnum

logger = logging.getLogger(__name__)
settings = get_settings()

# Configuration du hachage de mots de passe
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service d'authentification pour les utilisateurs locaux."""

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db

    # === Password Management ===

    def hash_password(self, password: str) -> str:
        """Hache un mot de passe avec bcrypt."""
        # bcrypt limite à 72 bytes, tronquer si nécessaire
        password_bytes = password.encode('utf-8')[:72]
        return pwd_context.hash(password_bytes.decode('utf-8', errors='ignore'))

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Vérifie un mot de passe contre son hash."""
        # bcrypt limite à 72 bytes, tronquer comme lors du hashage
        password_bytes = plain_password.encode('utf-8')[:72]
        return pwd_context.verify(password_bytes.decode('utf-8', errors='ignore'), hashed_password)

    def validate_password_strength(self, password: str) -> Tuple[bool, list]:
        """
        Valide la force d'un mot de passe selon la politique.

        Returns:
            Tuple (is_valid, list of errors)
        """
        errors = []

        if len(password) < settings.password_min_length:
            errors.append(f"Le mot de passe doit contenir au moins {settings.password_min_length} caractères")

        if settings.password_require_uppercase and not any(c.isupper() for c in password):
            errors.append("Le mot de passe doit contenir au moins une majuscule")

        if settings.password_require_lowercase and not any(c.islower() for c in password):
            errors.append("Le mot de passe doit contenir au moins une minuscule")

        if settings.password_require_digit and not any(c.isdigit() for c in password):
            errors.append("Le mot de passe doit contenir au moins un chiffre")

        if settings.password_require_special:
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if not any(c in special_chars for c in password):
                errors.append("Le mot de passe doit contenir au moins un caractère spécial")

        return len(errors) == 0, errors

    # === JWT Token Management ===

    def create_access_token(
        self,
        user_id: str,
        session_id: str,
        role: str,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Crée un access token JWT.

        Args:
            user_id: ID de l'utilisateur
            session_id: ID de la session
            role: Rôle de l'utilisateur
            expires_delta: Durée de validité optionnelle
        """
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)

        to_encode = {
            "sub": user_id,
            "session_id": session_id,
            "role": role,
            "type": "access",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }

        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    def create_refresh_token(self, session_id: str) -> str:
        """
        Crée un refresh token JWT.

        Args:
            session_id: ID de la session
        """
        expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

        to_encode = {
            "session_id": session_id,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }

        return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Vérifie et décode un token JWT.

        Returns:
            Payload du token ou None si invalide
        """
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            return payload
        except JWTError as e:
            logger.debug(f"JWT verification failed: {e}")
            return None

    def hash_token(self, token: str) -> str:
        """Hash un token pour stockage en base."""
        return hashlib.sha256(token.encode()).hexdigest()

    # === Session Management ===

    async def create_session(
        self,
        user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[UserSession, str]:
        """
        Crée une nouvelle session utilisateur.

        Args:
            user: Utilisateur
            ip_address: Adresse IP du client
            user_agent: User-Agent du client

        Returns:
            Tuple (session, refresh_token)
        """
        # Vérifier le nombre de sessions actives
        active_sessions = await self.db.execute(
            select(func.count()).where(
                UserSession.user_id == user.id,
                UserSession.is_valid == True
            )
        )
        count = active_sessions.scalar() or 0

        # Supprimer les anciennes sessions si limite atteinte
        if count >= settings.max_sessions_per_user:
            # Supprimer la session la plus ancienne
            oldest = await self.db.execute(
                select(UserSession)
                .where(UserSession.user_id == user.id, UserSession.is_valid == True)
                .order_by(UserSession.created_at.asc())
                .limit(1)
            )
            oldest_session = oldest.scalar_one_or_none()
            if oldest_session:
                oldest_session.is_valid = False
                oldest_session.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # Créer la nouvelle session
        session_id = str(uuid.uuid4())
        refresh_token = self.create_refresh_token(session_id)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)).replace(tzinfo=None)

        session = UserSession(
            id=session_id,
            user_id=user.id,
            refresh_token_hash=self.hash_token(refresh_token),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,  # Already naive UTC
            is_valid=True,
        )

        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        return session, refresh_token

    async def validate_session(self, session_id: str) -> Optional[UserSession]:
        """
        Valide une session.

        Returns:
            Session si valide, None sinon
        """
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.is_valid == True,
                UserSession.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
            )
        )
        session = result.scalar_one_or_none()

        if session:
            # Mettre à jour last_used_at
            session.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self.db.commit()

        return session

    async def revoke_session(self, session_id: str) -> bool:
        """Révoque une session."""
        result = await self.db.execute(
            select(UserSession).where(UserSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if session:
            session.is_valid = False
            session.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await self.db.commit()
            return True

        return False

    async def revoke_all_sessions(self, user_id: str, except_session_id: Optional[str] = None) -> int:
        """
        Révoque toutes les sessions d'un utilisateur.

        Args:
            user_id: ID de l'utilisateur
            except_session_id: Session à exclure (pour garder la session courante)

        Returns:
            Nombre de sessions révoquées
        """
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.is_valid == True
        )

        if except_session_id:
            query = query.where(UserSession.id != except_session_id)

        result = await self.db.execute(query)
        sessions = result.scalars().all()

        count = 0
        for session in sessions:
            session.is_valid = False
            session.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            count += 1

        if count > 0:
            await self.db.commit()

        return count

    async def cleanup_expired_sessions(self) -> int:
        """
        Supprime les sessions expirées.

        Returns:
            Nombre de sessions supprimées
        """
        result = await self.db.execute(
            delete(UserSession).where(UserSession.expires_at < datetime.now(timezone.utc).replace(tzinfo=None))
        )
        await self.db.commit()
        return result.rowcount

    # === User Authentication ===

    async def authenticate_user(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[User], Optional[UserSession], Optional[str], Optional[str]]:
        """
        Authentifie un utilisateur avec username/password.

        Returns:
            Tuple (user, session, access_token, refresh_token) ou (None, None, None, error_message)
        """
        # Chercher l'utilisateur
        result = await self.db.execute(
            select(User).where(
                (User.username == username) | (User.email == username)
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None, None, None, "Identifiants invalides"

        # Vérifier si le compte est actif
        if not user.is_active:
            return None, None, None, "Compte désactivé"

        # Vérifier le verrouillage
        if user.is_locked:
            now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
            if user.locked_until and user.locked_until > now_naive:
                remaining = (user.locked_until - now_naive).seconds // 60
                return None, None, None, f"Compte verrouillé. Réessayez dans {remaining} minutes"
            else:
                # Déverrouiller automatiquement
                user.is_locked = False
                user.failed_login_attempts = 0
                user.locked_until = None

        # Vérifier que c'est un utilisateur local (avec password)
        if not user.password_hash:
            return None, None, None, "Utilisateur SSO, utilisez la connexion SSO"

        # Vérifier le mot de passe
        if not self.verify_password(password, user.password_hash):
            await self._record_failed_attempt(user)
            return None, None, None, "Identifiants invalides"

        # Réinitialiser les tentatives échouées
        user.failed_login_attempts = 0
        user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

        # Créer la session et les tokens
        session, refresh_token = await self.create_session(user, ip_address, user_agent)
        access_token = self.create_access_token(user.id, session.id, user.role.value)

        return user, session, access_token, refresh_token

    async def refresh_access_token(
        self,
        refresh_token: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Rafraîchit un access token à partir d'un refresh token.

        Returns:
            Tuple (new_access_token, new_refresh_token, error_message)
        """
        # Vérifier le refresh token
        payload = self.verify_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None, None, "Refresh token invalide"

        session_id = payload.get("session_id")
        if not session_id:
            return None, None, "Refresh token invalide"

        # Vérifier la session
        session = await self.validate_session(session_id)
        if not session:
            return None, None, "Session expirée ou invalide"

        # Vérifier le hash du token
        if session.refresh_token_hash != self.hash_token(refresh_token):
            return None, None, "Refresh token invalide"

        # Charger l'utilisateur
        result = await self.db.execute(
            select(User).where(User.id == session.user_id)
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            await self.revoke_session(session_id)
            return None, None, "Utilisateur inactif"

        # Générer de nouveaux tokens
        new_access_token = self.create_access_token(user.id, session.id, user.role.value)

        # Optionnel: rotation du refresh token (plus sécurisé)
        new_refresh_token = self.create_refresh_token(session.id)
        session.refresh_token_hash = self.hash_token(new_refresh_token)
        await self.db.commit()

        return new_access_token, new_refresh_token, None

    async def _record_failed_attempt(self, user: User):
        """Enregistre une tentative de connexion échouée."""
        user.failed_login_attempts += 1

        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.is_locked = True
            user.locked_until = (datetime.now(timezone.utc) + timedelta(minutes=settings.lockout_duration_minutes)).replace(tzinfo=None)
            logger.warning(f"User {user.username} locked after {user.failed_login_attempts} failed attempts")

        await self.db.commit()

    # === Token Creation for Users ===

    async def create_tokens_for_user(
        self,
        user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[str, str, UserSession]:
        """
        Crée des tokens pour un utilisateur (utilisé après SSO).

        Returns:
            Tuple (access_token, refresh_token, session)
        """
        session, refresh_token = await self.create_session(user, ip_address, user_agent)
        access_token = self.create_access_token(user.id, session.id, user.role.value)

        # Mettre à jour last_login
        user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.db.commit()

        return access_token, refresh_token, session

    async def logout_all_sessions(self, user_id: str) -> int:
        """
        Révoque toutes les sessions d'un utilisateur.
        Alias de revoke_all_sessions pour compatibilité API.

        Returns:
            Nombre de sessions révoquées
        """
        return await self.revoke_all_sessions(user_id)
