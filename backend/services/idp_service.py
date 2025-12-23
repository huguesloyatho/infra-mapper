"""Service pour la gestion des fournisseurs d'identité (OIDC, SAML)."""

import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from db.auth_models import IdentityProvider, IdentityProviderType, RoleEnum


class IdentityProviderService:
    """Service pour gérer les providers d'identité."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_provider(
        self,
        name: str,
        display_name: str,
        provider_type: IdentityProviderType,
        config: dict,
        is_enabled: bool = False,
        attribute_mapping: Optional[dict] = None,
        role_mapping: Optional[dict] = None,
        auto_create_users: bool = True,
        default_role: RoleEnum = RoleEnum.VIEWER,
    ) -> IdentityProvider:
        """Crée un nouveau provider d'identité."""
        provider = IdentityProvider(
            id=str(uuid.uuid4()),
            name=name,
            display_name=display_name,
            provider_type=provider_type,
            config=config,
            is_enabled=is_enabled,
            attribute_mapping=attribute_mapping or {},
            role_mapping=role_mapping or {},
            auto_create_users=auto_create_users,
            default_role=default_role,
        )

        self.db.add(provider)
        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def get_provider(self, provider_id: str) -> Optional[IdentityProvider]:
        """Récupère un provider par ID."""
        result = await self.db.execute(
            select(IdentityProvider).where(IdentityProvider.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def get_provider_by_name(self, name: str) -> Optional[IdentityProvider]:
        """Récupère un provider par son slug."""
        result = await self.db.execute(
            select(IdentityProvider).where(IdentityProvider.name == name)
        )
        return result.scalar_one_or_none()

    async def update_provider(
        self,
        provider_id: str,
        display_name: Optional[str] = None,
        config: Optional[dict] = None,
        is_enabled: Optional[bool] = None,
        attribute_mapping: Optional[dict] = None,
        role_mapping: Optional[dict] = None,
        auto_create_users: Optional[bool] = None,
        default_role: Optional[RoleEnum] = None,
    ) -> Optional[IdentityProvider]:
        """Met à jour un provider."""
        provider = await self.get_provider(provider_id)
        if not provider:
            return None

        if display_name is not None:
            provider.display_name = display_name
        if config is not None:
            provider.config = config
        if is_enabled is not None:
            provider.is_enabled = is_enabled
        if attribute_mapping is not None:
            provider.attribute_mapping = attribute_mapping
        if role_mapping is not None:
            provider.role_mapping = role_mapping
        if auto_create_users is not None:
            provider.auto_create_users = auto_create_users
        if default_role is not None:
            provider.default_role = default_role

        await self.db.flush()
        await self.db.refresh(provider)
        return provider

    async def delete_provider(self, provider_id: str) -> bool:
        """Supprime un provider."""
        provider = await self.get_provider(provider_id)
        if not provider:
            return False

        await self.db.delete(provider)
        return True

    async def list_providers(
        self,
        include_disabled: bool = False,
        provider_type: Optional[IdentityProviderType] = None,
    ) -> List[IdentityProvider]:
        """Liste les providers."""
        query = select(IdentityProvider)

        if not include_disabled:
            query = query.where(IdentityProvider.is_enabled == True)
        if provider_type:
            query = query.where(IdentityProvider.provider_type == provider_type)

        query = query.order_by(IdentityProvider.display_name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def enable_provider(self, provider_id: str) -> bool:
        """Active un provider."""
        provider = await self.get_provider(provider_id)
        if not provider:
            return False

        provider.is_enabled = True
        await self.db.flush()
        return True

    async def disable_provider(self, provider_id: str) -> bool:
        """Désactive un provider."""
        provider = await self.get_provider(provider_id)
        if not provider:
            return False

        provider.is_enabled = False
        # Retirer le statut par défaut si désactivé
        provider.is_default = False
        await self.db.flush()
        return True

    async def set_default_provider(self, provider_id: str) -> bool:
        """Définit un provider comme provider par défaut pour SSO."""
        provider = await self.get_provider(provider_id)
        if not provider or not provider.is_enabled:
            return False

        # Retirer le statut par défaut des autres providers
        await self.db.execute(
            update(IdentityProvider)
            .where(IdentityProvider.id != provider_id)
            .values(is_default=False)
        )

        provider.is_default = True
        await self.db.flush()
        return True

    async def get_default_provider(self) -> Optional[IdentityProvider]:
        """Récupère le provider par défaut."""
        result = await self.db.execute(
            select(IdentityProvider)
            .where(IdentityProvider.is_default == True)
            .where(IdentityProvider.is_enabled == True)
        )
        return result.scalar_one_or_none()

    async def get_enabled_providers_for_login(self) -> List[dict]:
        """Récupère les providers activés pour la page de login (info publique)."""
        providers = await self.list_providers(include_disabled=False)
        return [
            {
                "id": p.id,
                "name": p.name,
                "display_name": p.display_name,
                "provider_type": p.provider_type.value,
                "is_default": p.is_default,
            }
            for p in providers
        ]
