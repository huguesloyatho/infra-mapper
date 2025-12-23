"""Service de gestion des utilisateurs."""

import logging
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.auth_models import User, UserSession, RoleEnum
from services.auth_service import AuthService

logger = logging.getLogger(__name__)
settings = get_settings()


class UserService:
    """Service CRUD pour les utilisateurs."""

    def __init__(self, db: AsyncSession):
        """Initialise le service."""
        self.db = db
        self.auth_service = AuthService(db)

    # === CRUD Operations ===

    async def create_user(
        self,
        username: str,
        email: str,
        password: Optional[str] = None,
        role: RoleEnum = RoleEnum.VIEWER,
        display_name: Optional[str] = None,
        idp_id: Optional[str] = None,
        external_id: Optional[str] = None,
    ) -> User:
        """
        Crée un nouvel utilisateur.

        Args:
            username: Nom d'utilisateur unique
            email: Email unique
            password: Mot de passe (None pour utilisateurs SSO)
            role: Rôle de l'utilisateur
            display_name: Nom affiché
            idp_id: ID du fournisseur d'identité (pour SSO)
            external_id: ID externe chez le fournisseur

        Returns:
            Utilisateur créé
        """
        # Valider le mot de passe si fourni
        password_hash = None
        if password:
            is_valid, errors = self.auth_service.validate_password_strength(password)
            if not is_valid:
                raise ValueError(f"Mot de passe invalide: {', '.join(errors)}")
            password_hash = self.auth_service.hash_password(password)

        user = User(
            id=str(uuid.uuid4()),
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            display_name=display_name or username,
            idp_id=idp_id,
            external_id=external_id,
            is_active=True,
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"User created: {username} (role: {role.value})")
        return user

    async def get_user(self, user_id: str) -> Optional[User]:
        """Récupère un utilisateur par ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Récupère un utilisateur par username."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Récupère un utilisateur par email."""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 50,
        role: Optional[RoleEnum] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> tuple[List[User], int]:
        """
        Liste les utilisateurs avec filtres et pagination.

        Returns:
            Tuple (users, total)
        """
        query = select(User)

        if role:
            query = query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                (User.username.ilike(search_pattern)) |
                (User.email.ilike(search_pattern)) |
                (User.display_name.ilike(search_pattern))
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Get page
        query = query.order_by(User.username).offset(skip).limit(limit)
        result = await self.db.execute(query)
        users = list(result.scalars().all())

        return users, total

    async def update_user(
        self,
        user_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        role: Optional[RoleEnum] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[User]:
        """
        Met à jour un utilisateur.

        Returns:
            Utilisateur mis à jour ou None si non trouvé
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        if username is not None:
            user.username = username
        if email is not None:
            user.email = email
        if display_name is not None:
            user.display_name = display_name
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active

        user.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"User updated: {user.username}")
        return user

    async def delete_user(self, user_id: str) -> bool:
        """
        Supprime un utilisateur.

        Returns:
            True si supprimé, False si non trouvé
        """
        user = await self.get_user(user_id)
        if not user:
            return False

        username = user.username
        await self.db.delete(user)
        await self.db.commit()

        logger.info(f"User deleted: {username}")
        return True

    # === Password Management ===

    async def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str
    ) -> tuple[bool, Optional[str]]:
        """
        Change le mot de passe d'un utilisateur.

        Returns:
            Tuple (success, error_message)
        """
        user = await self.get_user(user_id)
        if not user:
            return False, "Utilisateur non trouvé"

        if not user.password_hash:
            return False, "Utilisateur SSO, impossible de changer le mot de passe"

        # Vérifier le mot de passe actuel
        if not self.auth_service.verify_password(current_password, user.password_hash):
            return False, "Mot de passe actuel incorrect"

        # Valider le nouveau mot de passe
        is_valid, errors = self.auth_service.validate_password_strength(new_password)
        if not is_valid:
            return False, f"Nouveau mot de passe invalide: {', '.join(errors)}"

        # Mettre à jour
        user.password_hash = self.auth_service.hash_password(new_password)
        user.updated_at = datetime.utcnow()
        await self.db.commit()

        logger.info(f"Password changed for user: {user.username}")
        return True, None

    async def reset_password(
        self,
        user_id: str,
        new_password: str
    ) -> tuple[bool, Optional[str]]:
        """
        Réinitialise le mot de passe d'un utilisateur (admin only).

        Returns:
            Tuple (success, error_message)
        """
        user = await self.get_user(user_id)
        if not user:
            return False, "Utilisateur non trouvé"

        # Valider le nouveau mot de passe
        is_valid, errors = self.auth_service.validate_password_strength(new_password)
        if not is_valid:
            return False, f"Mot de passe invalide: {', '.join(errors)}"

        # Mettre à jour
        user.password_hash = self.auth_service.hash_password(new_password)
        user.updated_at = datetime.utcnow()

        # Révoquer toutes les sessions existantes
        await self.auth_service.revoke_all_sessions(user_id)

        await self.db.commit()

        logger.info(f"Password reset for user: {user.username}")
        return True, None

    # === Role Management ===

    async def change_role(
        self,
        user_id: str,
        new_role: RoleEnum
    ) -> Optional[User]:
        """
        Change le rôle d'un utilisateur.

        Returns:
            Utilisateur mis à jour ou None
        """
        user = await self.get_user(user_id)
        if not user:
            return None

        old_role = user.role
        user.role = new_role
        user.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"Role changed for {user.username}: {old_role.value} -> {new_role.value}")
        return user

    # === Account Status ===

    async def activate_user(self, user_id: str) -> Optional[User]:
        """Active un compte utilisateur."""
        return await self.update_user(user_id, is_active=True)

    async def deactivate_user(self, user_id: str) -> Optional[User]:
        """Désactive un compte utilisateur et révoque ses sessions."""
        user = await self.get_user(user_id)
        if not user:
            return None

        user.is_active = False
        user.updated_at = datetime.utcnow()

        # Révoquer toutes les sessions
        await self.auth_service.revoke_all_sessions(user_id)

        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"User deactivated: {user.username}")
        return user

    async def unlock_user(self, user_id: str) -> Optional[User]:
        """Déverrouille un compte utilisateur."""
        user = await self.get_user(user_id)
        if not user:
            return None

        user.is_locked = False
        user.failed_login_attempts = 0
        user.locked_until = None
        user.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"User unlocked: {user.username}")
        return user

    # === SSO User Management ===

    async def find_or_create_sso_user(
        self,
        idp_id: str,
        external_id: str,
        email: str,
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        role: Optional[RoleEnum] = None,
    ) -> User:
        """
        Trouve ou crée un utilisateur SSO.

        Args:
            idp_id: ID du fournisseur d'identité
            external_id: ID de l'utilisateur chez le fournisseur
            email: Email de l'utilisateur
            username: Nom d'utilisateur (défaut: email)
            display_name: Nom affiché
            role: Rôle (défaut: VIEWER)

        Returns:
            Utilisateur existant ou nouvellement créé
        """
        # Chercher par idp_id + external_id
        result = await self.db.execute(
            select(User).where(
                User.idp_id == idp_id,
                User.external_id == external_id
            )
        )
        user = result.scalar_one_or_none()

        if user:
            # Mettre à jour les infos
            user.email = email
            if display_name:
                user.display_name = display_name
            user.last_login = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(user)
            return user

        # Chercher par email (lier un utilisateur existant)
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        user = result.scalar_one_or_none()

        if user:
            # Lier l'utilisateur existant au SSO
            user.idp_id = idp_id
            user.external_id = external_id
            if display_name:
                user.display_name = display_name
            user.last_login = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(user)
            logger.info(f"Existing user linked to SSO: {user.username}")
            return user

        # Créer un nouvel utilisateur
        final_username = username or email.split("@")[0]

        # Assurer l'unicité du username
        base_username = final_username
        counter = 1
        while await self.get_user_by_username(final_username):
            final_username = f"{base_username}{counter}"
            counter += 1

        user = await self.create_user(
            username=final_username,
            email=email,
            password=None,  # Pas de password pour SSO
            role=role or RoleEnum.VIEWER,
            display_name=display_name or final_username,
            idp_id=idp_id,
            external_id=external_id,
        )

        logger.info(f"SSO user created: {user.username}")
        return user

    # === Session Management ===

    async def get_user_sessions(self, user_id: str) -> List[UserSession]:
        """Récupère toutes les sessions actives d'un utilisateur."""
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.is_valid == True
            ).order_by(UserSession.last_used_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_user_sessions(self, user_id: str) -> int:
        """Révoque toutes les sessions d'un utilisateur."""
        return await self.auth_service.revoke_all_sessions(user_id)


async def create_initial_admin(db: AsyncSession) -> Optional[User]:
    """
    Crée l'utilisateur admin initial si configuré.

    Appelé au démarrage de l'application.
    """
    if not settings.initial_admin_password:
        return None

    user_service = UserService(db)

    # Vérifier si l'admin existe déjà
    existing = await user_service.get_user_by_username(settings.initial_admin_username)
    if existing:
        logger.debug(f"Initial admin already exists: {settings.initial_admin_username}")
        return existing

    # Créer l'admin initial en tant que SUPER_ADMIN
    try:
        admin = await user_service.create_user(
            username=settings.initial_admin_username,
            email=settings.initial_admin_email,
            password=settings.initial_admin_password,
            role=RoleEnum.SUPER_ADMIN,
            display_name="Super Administrator",
        )
        logger.info(f"Initial super admin created: {admin.username}")
        return admin
    except Exception as e:
        logger.error(f"Failed to create initial admin: {e}")
        return None
