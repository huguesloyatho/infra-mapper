"""Routes API pour la gestion des Identity Providers (Admin only)."""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.auth_models import User, IdentityProviderType, RoleEnum
from services.idp_service import IdentityProviderService
from services.audit_service import AuditService, AuditActionType
from api.dependencies import require_admin_or_bypass

router = APIRouter(prefix="/api/v1/identity-providers", tags=["identity-providers"])


# Schemas
class OIDCConfig(BaseModel):
    client_id: str
    client_secret: Optional[str] = None
    issuer_url: str
    scopes: str = "openid profile email"
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None


class SAMLConfig(BaseModel):
    entity_id: str
    sso_url: str
    slo_url: Optional[str] = None
    certificate: str
    name_id_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"


class IdpCreate(BaseModel):
    name: str
    display_name: str
    provider_type: str  # "oidc" or "saml"
    is_enabled: bool = False
    config: dict
    attribute_mapping: Optional[dict] = None
    role_mapping: Optional[dict] = None
    auto_create_users: bool = True
    default_role: str = "viewer"


class IdpUpdate(BaseModel):
    display_name: Optional[str] = None
    is_enabled: Optional[bool] = None
    config: Optional[dict] = None
    attribute_mapping: Optional[dict] = None
    role_mapping: Optional[dict] = None
    auto_create_users: Optional[bool] = None
    default_role: Optional[str] = None


class IdpResponse(BaseModel):
    id: str
    name: str
    display_name: str
    provider_type: str
    is_enabled: bool
    is_default: bool
    config: dict
    attribute_mapping: dict
    role_mapping: dict
    auto_create_users: bool
    default_role: str

    class Config:
        from_attributes = True


class DiscoverOIDCRequest(BaseModel):
    issuer_url: str


@router.get("", response_model=List[IdpResponse])
async def list_providers(
    include_disabled: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Liste tous les providers d'identité (admin only)."""
    idp_service = IdentityProviderService(db)
    providers = await idp_service.list_providers(include_disabled=include_disabled)

    return [
        IdpResponse(
            id=p.id,
            name=p.name,
            display_name=p.display_name,
            provider_type=p.provider_type.value,
            is_enabled=p.is_enabled,
            is_default=p.is_default,
            config=p.config,
            attribute_mapping=p.attribute_mapping,
            role_mapping=p.role_mapping,
            auto_create_users=p.auto_create_users,
            default_role=p.default_role.value,
        )
        for p in providers
    ]


@router.post("", response_model=IdpResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    data: IdpCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Crée un nouveau provider d'identité (admin only)."""
    idp_service = IdentityProviderService(db)
    audit_service = AuditService(db)

    # Vérifier que le nom n'existe pas
    existing = await idp_service.get_provider_by_name(data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un provider avec ce nom existe déjà"
        )

    # Valider le type
    try:
        provider_type = IdentityProviderType(data.provider_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type de provider invalide: {data.provider_type}"
        )

    # Valider le rôle par défaut
    try:
        default_role = RoleEnum(data.default_role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rôle invalide: {data.default_role}"
        )

    provider = await idp_service.create_provider(
        name=data.name,
        display_name=data.display_name,
        provider_type=provider_type,
        config=data.config,
        is_enabled=data.is_enabled,
        attribute_mapping=data.attribute_mapping,
        role_mapping=data.role_mapping,
        auto_create_users=data.auto_create_users,
        default_role=default_role,
    )

    # Log audit
    await audit_service.log(
        action=AuditActionType.IDP_CONFIG,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"action": "create", "provider_id": provider.id, "name": provider.name},
        success=True,
    )

    return IdpResponse(
        id=provider.id,
        name=provider.name,
        display_name=provider.display_name,
        provider_type=provider.provider_type.value,
        is_enabled=provider.is_enabled,
        is_default=provider.is_default,
        config=provider.config,
        attribute_mapping=provider.attribute_mapping,
        role_mapping=provider.role_mapping,
        auto_create_users=provider.auto_create_users,
        default_role=provider.default_role.value,
    )


@router.get("/{provider_id}", response_model=IdpResponse)
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Récupère un provider par ID (admin only)."""
    idp_service = IdentityProviderService(db)
    provider = await idp_service.get_provider(provider_id)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider non trouvé"
        )

    return IdpResponse(
        id=provider.id,
        name=provider.name,
        display_name=provider.display_name,
        provider_type=provider.provider_type.value,
        is_enabled=provider.is_enabled,
        is_default=provider.is_default,
        config=provider.config,
        attribute_mapping=provider.attribute_mapping,
        role_mapping=provider.role_mapping,
        auto_create_users=provider.auto_create_users,
        default_role=provider.default_role.value,
    )


@router.put("/{provider_id}", response_model=IdpResponse)
async def update_provider(
    provider_id: str,
    data: IdpUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Met à jour un provider (admin only)."""
    idp_service = IdentityProviderService(db)
    audit_service = AuditService(db)

    # Valider le rôle si fourni
    default_role = None
    if data.default_role:
        try:
            default_role = RoleEnum(data.default_role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Rôle invalide: {data.default_role}"
            )

    provider = await idp_service.update_provider(
        provider_id=provider_id,
        display_name=data.display_name,
        config=data.config,
        is_enabled=data.is_enabled,
        attribute_mapping=data.attribute_mapping,
        role_mapping=data.role_mapping,
        auto_create_users=data.auto_create_users,
        default_role=default_role,
    )

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider non trouvé"
        )

    # Log audit
    await audit_service.log(
        action=AuditActionType.IDP_CONFIG,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"action": "update", "provider_id": provider_id},
        success=True,
    )

    return IdpResponse(
        id=provider.id,
        name=provider.name,
        display_name=provider.display_name,
        provider_type=provider.provider_type.value,
        is_enabled=provider.is_enabled,
        is_default=provider.is_default,
        config=provider.config,
        attribute_mapping=provider.attribute_mapping,
        role_mapping=provider.role_mapping,
        auto_create_users=provider.auto_create_users,
        default_role=provider.default_role.value,
    )


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Supprime un provider (admin only)."""
    idp_service = IdentityProviderService(db)
    audit_service = AuditService(db)

    provider = await idp_service.get_provider(provider_id)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider non trouvé"
        )

    await idp_service.delete_provider(provider_id)

    # Log audit
    await audit_service.log(
        action=AuditActionType.IDP_CONFIG,
        user_id=current_user.id if current_user else None,
        ip_address=None,
        details={"action": "delete", "provider_id": provider_id, "name": provider.name},
        success=True,
    )


@router.post("/{provider_id}/enable")
async def enable_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Active un provider (admin only)."""
    idp_service = IdentityProviderService(db)

    success = await idp_service.enable_provider(provider_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider non trouvé"
        )

    return {"message": "Provider activé"}


@router.post("/{provider_id}/disable")
async def disable_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Désactive un provider (admin only)."""
    idp_service = IdentityProviderService(db)

    success = await idp_service.disable_provider(provider_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider non trouvé"
        )

    return {"message": "Provider désactivé"}


@router.post("/{provider_id}/set-default")
async def set_default_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """Définit un provider comme provider par défaut (admin only)."""
    idp_service = IdentityProviderService(db)

    success = await idp_service.set_default_provider(provider_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider non trouvé ou non activé"
        )

    return {"message": "Provider défini par défaut"}


@router.post("/discover-oidc")
async def discover_oidc(
    data: DiscoverOIDCRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(require_admin_or_bypass),
):
    """
    Découvre les endpoints OIDC à partir de l'issuer URL.
    Utilise la well-known configuration.
    """
    import httpx

    issuer_url = data.issuer_url.rstrip("/")
    discovery_url = f"{issuer_url}/.well-known/openid-configuration"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            config = response.json()

        return {
            "issuer": config.get("issuer"),
            "authorization_endpoint": config.get("authorization_endpoint"),
            "token_endpoint": config.get("token_endpoint"),
            "userinfo_endpoint": config.get("userinfo_endpoint"),
            "jwks_uri": config.get("jwks_uri"),
            "scopes_supported": config.get("scopes_supported", []),
        }
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur découverte OIDC: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur inattendue: {str(e)}"
        )
