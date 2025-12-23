"""Schémas Pydantic pour l'authentification."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

from db.auth_models import RoleEnum, IdentityProviderType


# === Authentication ===

class LoginRequest(BaseModel):
    """Requête de connexion."""
    username: str = Field(..., min_length=1, description="Username ou email")
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Réponse avec tokens."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Durée de validité en secondes")


class RefreshRequest(BaseModel):
    """Requête de rafraîchissement de token."""
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Requête de changement de mot de passe."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class ResetPasswordRequest(BaseModel):
    """Requête de réinitialisation de mot de passe (admin)."""
    new_password: str = Field(..., min_length=8)


# === User ===

class UserBase(BaseModel):
    """Base pour les utilisateurs."""
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    display_name: Optional[str] = None
    role: RoleEnum = RoleEnum.VIEWER


class UserCreate(UserBase):
    """Création d'utilisateur."""
    password: Optional[str] = Field(None, min_length=8, description="Requis pour utilisateurs locaux")


class UserUpdate(BaseModel):
    """Mise à jour d'utilisateur."""
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """Réponse utilisateur."""
    id: str
    username: str
    email: str
    display_name: Optional[str]
    role: str
    is_active: bool
    is_locked: bool
    is_sso: bool = Field(description="True si utilisateur SSO")
    idp_name: Optional[str] = Field(None, description="Nom du provider SSO")
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === Session ===

class SessionResponse(BaseModel):
    """Réponse session."""
    id: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    is_current: bool = Field(description="True si c'est la session courante")
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


# === Identity Provider ===

class IdpBase(BaseModel):
    """Base pour les fournisseurs d'identité."""
    name: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    display_name: str = Field(..., min_length=1, max_length=255)
    provider_type: IdentityProviderType


class IdpConfigOIDC(BaseModel):
    """Configuration OIDC."""
    client_id: str
    client_secret: str
    issuer_url: str = Field(..., description="URL de l'issuer OIDC (ex: https://keycloak/realms/master)")
    scopes: List[str] = Field(default=["openid", "email", "profile"])
    # Auto-découverts depuis .well-known/openid-configuration
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None


class IdpConfigSAML(BaseModel):
    """Configuration SAML."""
    entity_id: str = Field(..., description="Entity ID du SP (Service Provider)")
    idp_entity_id: str = Field(..., description="Entity ID de l'IdP")
    sso_url: str = Field(..., description="Single Sign-On URL")
    slo_url: Optional[str] = Field(None, description="Single Logout URL")
    certificate: str = Field(..., description="Certificat X.509 de l'IdP (PEM)")
    name_id_format: str = Field(
        default="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    )
    sign_requests: bool = True
    want_assertions_signed: bool = True


class IdpCreate(IdpBase):
    """Création de fournisseur d'identité."""
    config: dict = Field(..., description="Configuration spécifique au type")
    attribute_mapping: dict = Field(
        default={"email": "email", "name": "name", "username": "preferred_username"},
        description="Mapping des attributs IdP vers User"
    )
    role_mapping: dict = Field(
        default={"*": "viewer"},
        description="Mapping des groupes IdP vers les rôles"
    )
    auto_create_users: bool = True
    default_role: RoleEnum = RoleEnum.VIEWER


class IdpUpdate(BaseModel):
    """Mise à jour de fournisseur d'identité."""
    display_name: Optional[str] = None
    config: Optional[dict] = None
    attribute_mapping: Optional[dict] = None
    role_mapping: Optional[dict] = None
    auto_create_users: Optional[bool] = None
    default_role: Optional[RoleEnum] = None
    is_enabled: Optional[bool] = None


class IdpResponse(BaseModel):
    """Réponse fournisseur d'identité."""
    id: str
    name: str
    display_name: str
    provider_type: str
    is_enabled: bool
    is_default: bool
    auto_create_users: bool
    default_role: str
    attribute_mapping: dict
    role_mapping: dict
    created_at: datetime
    updated_at: datetime
    # Ne pas exposer config qui contient des secrets

    class Config:
        from_attributes = True


class IdpPublicInfo(BaseModel):
    """Info publique d'un IdP pour la page de login."""
    id: str
    name: str
    display_name: str
    provider_type: str


class IdpDiscoverRequest(BaseModel):
    """Requête de découverte OIDC."""
    issuer_url: str


class IdpDiscoverResponse(BaseModel):
    """Réponse de découverte OIDC."""
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: Optional[str]
    jwks_uri: str
    scopes_supported: List[str]


class IdpTestResponse(BaseModel):
    """Réponse de test de connexion IdP."""
    success: bool
    message: str
    details: Optional[dict] = None


# === Audit ===

class AuditLogResponse(BaseModel):
    """Réponse log d'audit."""
    id: int
    timestamp: datetime
    user_id: Optional[str]
    username: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    ip_address: Optional[str]
    success: bool
    error_message: Optional[str]
    details: dict

    class Config:
        from_attributes = True


class AuditLogFilter(BaseModel):
    """Filtres pour les logs d'audit."""
    action: Optional[str] = None
    user_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    success: Optional[bool] = None


# === Auth Providers List (for login page) ===

class AuthProvidersResponse(BaseModel):
    """Liste des providers auth disponibles."""
    local_enabled: bool = True
    providers: List[IdpPublicInfo] = []


# === Additional schemas for user routes ===

class PasswordReset(BaseModel):
    """Schéma pour réinitialisation mot de passe admin."""
    new_password: str = Field(..., min_length=8)


class RoleChange(BaseModel):
    """Schéma pour changement de rôle."""
    role: str


# === 2FA / TOTP ===

class TOTPSetupResponse(BaseModel):
    """Réponse pour l'initialisation du 2FA."""
    secret: str = Field(..., description="Secret TOTP en base32 (à afficher si QR code ne fonctionne pas)")
    qr_code: str = Field(..., description="QR code en base64 (data URI)")
    backup_codes: List[str] = Field(..., description="Codes de secours (à sauvegarder)")


class TOTPVerifyRequest(BaseModel):
    """Requête de vérification de code TOTP."""
    code: str = Field(..., min_length=6, max_length=8, description="Code TOTP à 6 chiffres ou code de secours")


class TOTPDisableRequest(BaseModel):
    """Requête de désactivation du 2FA."""
    password: str = Field(..., min_length=1, description="Mot de passe pour confirmer")


class LoginResponse(BaseModel):
    """Réponse de connexion (peut nécessiter 2FA)."""
    requires_2fa: bool = Field(default=False, description="True si 2FA requis")
    temp_token: Optional[str] = Field(None, description="Token temporaire pour compléter le 2FA")
    # Présents uniquement si 2FA non requis
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: Optional[int] = Field(None, description="Durée de validité en secondes")


class Login2FARequest(BaseModel):
    """Requête de vérification 2FA après login initial."""
    temp_token: str = Field(..., description="Token temporaire reçu lors du login")
    code: str = Field(..., min_length=6, max_length=10, description="Code TOTP ou code de secours")


class UserMeResponse(UserResponse):
    """Réponse pour l'utilisateur courant (/me)."""
    sessions_count: int = Field(description="Nombre de sessions actives")
    totp_enabled: bool = Field(default=False, description="2FA activé")
