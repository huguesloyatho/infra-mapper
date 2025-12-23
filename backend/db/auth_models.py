"""Modèles SQLAlchemy pour l'authentification et l'autorisation."""

import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


# === Enums ===

class RoleEnum(str, enum.Enum):
    """Rôles utilisateur."""
    SUPER_ADMIN = "super_admin"  # Peut gérer toutes les organisations
    ADMIN = "admin"              # Admin de son organisation
    OPERATOR = "operator"
    VIEWER = "viewer"


class OrganizationRole(str, enum.Enum):
    """Rôles au sein d'une organisation."""
    OWNER = "owner"      # Propriétaire, peut tout faire
    ADMIN = "admin"      # Admin de l'organisation
    MEMBER = "member"    # Membre standard


class TeamRole(str, enum.Enum):
    """Rôles au sein d'une équipe."""
    LEAD = "lead"        # Chef d'équipe
    MEMBER = "member"    # Membre


class IdentityProviderType(str, enum.Enum):
    """Types de fournisseurs d'identité."""
    LOCAL = "local"
    OIDC = "oidc"
    SAML = "saml"


class AuditActionType(str, enum.Enum):
    """Types d'actions auditées."""
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    ROLE_CHANGE = "role_change"
    IDP_CONFIG = "idp_config"
    TOKEN_REFRESH = "token_refresh"
    SESSION_REVOKE = "session_revoke"
    TOTP_SETUP = "totp_setup"
    TOTP_ENABLED = "totp_enabled"
    TOTP_DISABLED = "totp_disabled"
    TOTP_FAILED = "totp_failed"


# === Models ===

class User(Base):
    """Table des utilisateurs."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)  # UUID
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Null pour les utilisateurs SSO
    role = Column(SQLEnum(RoleEnum, values_callable=lambda x: [e.value for e in x]), default=RoleEnum.VIEWER, nullable=False)

    # Lien vers le fournisseur d'identité (null pour utilisateurs locaux)
    idp_id = Column(String, ForeignKey("identity_providers.id", ondelete="SET NULL"), nullable=True)
    external_id = Column(String(255), nullable=True)  # ID chez le fournisseur externe

    # Statut du compte
    is_active = Column(Boolean, default=True)
    is_locked = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)

    # 2FA / TOTP
    totp_secret = Column(String(32), nullable=True)  # Secret TOTP encodé base32
    totp_enabled = Column(Boolean, default=False)  # 2FA activé
    totp_backup_codes = Column(JSON, nullable=True)  # Codes de secours hashés

    # Informations de profil
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)

    # Métadonnées
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relations
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    identity_provider = relationship("IdentityProvider", back_populates="users")

    # Index
    __table_args__ = (
        Index("ix_users_idp_external", "idp_id", "external_id"),
    )


class UserSession(Base):
    """Table des sessions utilisateur (pour tracking et révocation des tokens)."""

    __tablename__ = "user_sessions"

    id = Column(String, primary_key=True)  # UUID - utilisé comme jti du refresh token
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Hash du refresh token (pour validation)
    refresh_token_hash = Column(String(255), nullable=False)

    # Informations sur le client
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(String(500), nullable=True)
    device_info = Column(JSON, default=dict)

    # Statut
    is_valid = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    last_used_at = Column(DateTime, default=func.now())
    revoked_at = Column(DateTime, nullable=True)

    # Relations
    user = relationship("User", back_populates="sessions")

    # Index
    __table_args__ = (
        Index("ix_sessions_user_valid", "user_id", "is_valid"),
        Index("ix_sessions_expires", "expires_at"),
    )


class IdentityProvider(Base):
    """Table des fournisseurs d'identité (OIDC, SAML)."""

    __tablename__ = "identity_providers"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String(100), unique=True, nullable=False)  # Slug unique (ex: "keycloak", "azure-ad")
    display_name = Column(String(255), nullable=False)  # Nom affiché (ex: "Keycloak SSO")
    provider_type = Column(SQLEnum(IdentityProviderType), nullable=False)

    # Statut
    is_enabled = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)  # Provider par défaut pour SSO

    # Configuration (JSON chiffré recommandé en production)
    # Pour OIDC: client_id, client_secret, issuer_url, scopes, authorization_endpoint, token_endpoint, userinfo_endpoint
    # Pour SAML: entity_id, sso_url, slo_url, certificate, name_id_format
    config = Column(JSON, nullable=False, default=dict)

    # Mapping des attributs (comment les claims IdP sont mappés vers les champs User)
    # Ex: {"email": "email", "name": "displayName", "username": "preferred_username"}
    attribute_mapping = Column(JSON, default=dict)

    # Mapping des rôles (groupes/rôles IdP vers rôles locaux)
    # Ex: {"admins": "admin", "operators": "operator", "*": "viewer"}
    role_mapping = Column(JSON, default=dict)

    # Auto-provisioning
    auto_create_users = Column(Boolean, default=True)
    default_role = Column(SQLEnum(RoleEnum, values_callable=lambda x: [e.value for e in x]), default=RoleEnum.VIEWER)

    # Métadonnées
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_sync = Column(DateTime, nullable=True)

    # Relations
    users = relationship("User", back_populates="identity_provider")

    # Index
    __table_args__ = (
        Index("ix_idp_type_enabled", "provider_type", "is_enabled"),
    )


# =============================================================================
# MULTI-TENANCY: Organizations & Teams
# =============================================================================

class Organization(Base):
    """Table des organisations (tenants)."""

    __tablename__ = "organizations"

    id = Column(String, primary_key=True)  # UUID
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)  # URL-friendly
    description = Column(String(500), nullable=True)

    # Paramètres
    is_active = Column(Boolean, default=True)
    settings = Column(JSON, default=dict)
    # Ex: {"max_hosts": 10, "max_users": 20, "features": ["alerts", "reports"]}

    # Limites (quotas)
    max_hosts = Column(Integer, nullable=True)  # null = illimité
    max_users = Column(Integer, nullable=True)
    max_teams = Column(Integer, nullable=True)

    # Métadonnées
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relations
    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="organization", cascade="all, delete-orphan")
    hosts = relationship("OrganizationHost", back_populates="organization", cascade="all, delete-orphan")

    # Index
    __table_args__ = (
        Index("ix_organizations_active", "is_active"),
    )


class OrganizationMember(Base):
    """Table de liaison utilisateur <-> organisation."""

    __tablename__ = "organization_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Rôle dans l'organisation
    role = Column(SQLEnum(OrganizationRole), default=OrganizationRole.MEMBER, nullable=False)

    # Est-ce l'organisation par défaut de l'utilisateur ?
    is_default = Column(Boolean, default=False)

    # Métadonnées
    joined_at = Column(DateTime, default=func.now())
    invited_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relations
    organization = relationship("Organization", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])

    # Contrainte unique: un utilisateur ne peut être membre qu'une fois par org
    __table_args__ = (
        Index("ix_org_members_user", "user_id"),
        Index("ix_org_members_org_role", "organization_id", "role"),
        # Note: ajouter unique constraint sur (organization_id, user_id) via migration
    )


class Team(Base):
    """Table des équipes (sous-groupes dans une organisation)."""

    __tablename__ = "teams"

    id = Column(String, primary_key=True)  # UUID
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False)  # Unique au sein de l'org
    description = Column(String(500), nullable=True)

    # Paramètres
    is_active = Column(Boolean, default=True)
    color = Column(String(7), nullable=True)  # Couleur hex pour l'UI

    # Métadonnées
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relations
    organization = relationship("Organization", back_populates="teams")
    members = relationship("TeamMember", back_populates="team", cascade="all, delete-orphan")
    hosts = relationship("TeamHost", back_populates="team", cascade="all, delete-orphan")

    # Index
    __table_args__ = (
        Index("ix_teams_org_slug", "organization_id", "slug", unique=True),
        Index("ix_teams_active", "is_active"),
    )


class TeamMember(Base):
    """Table de liaison utilisateur <-> équipe."""

    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Rôle dans l'équipe
    role = Column(SQLEnum(TeamRole), default=TeamRole.MEMBER, nullable=False)

    # Métadonnées
    joined_at = Column(DateTime, default=func.now())
    added_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relations
    team = relationship("Team", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])

    # Index
    __table_args__ = (
        Index("ix_team_members_user", "user_id"),
        Index("ix_team_members_team_role", "team_id", "role"),
    )


class OrganizationHost(Base):
    """Liaison entre une organisation et ses hosts (pour isolation des données)."""

    __tablename__ = "organization_hosts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    host_id = Column(String, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)

    # Métadonnées
    assigned_at = Column(DateTime, default=func.now())
    assigned_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relations
    organization = relationship("Organization", back_populates="hosts")

    # Contrainte unique
    __table_args__ = (
        Index("ix_org_hosts_org", "organization_id"),
        Index("ix_org_hosts_host", "host_id", unique=True),  # Un host = une seule org
    )


class TeamHost(Base):
    """Liaison entre une équipe et les hosts qu'elle peut voir/gérer."""

    __tablename__ = "team_hosts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    host_id = Column(String, ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)

    # Permissions spécifiques à cette équipe pour ce host
    can_view = Column(Boolean, default=True)
    can_manage = Column(Boolean, default=False)  # Start/stop containers, etc.

    # Métadonnées
    assigned_at = Column(DateTime, default=func.now())

    # Relations
    team = relationship("Team", back_populates="hosts")

    # Index
    __table_args__ = (
        Index("ix_team_hosts_team", "team_id"),
        Index("ix_team_hosts_host", "host_id"),
    )


class AuditLog(Base):
    """Table des logs d'audit pour les actions de sécurité."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=func.now(), index=True)

    # Acteur (qui a fait l'action)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(100), nullable=True)  # Conservé même si l'utilisateur est supprimé
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Action
    action = Column(SQLEnum(AuditActionType), nullable=False)
    resource_type = Column(String(50), nullable=True)  # user, session, idp, etc.
    resource_id = Column(String, nullable=True)

    # Détails
    details = Column(JSON, default=dict)
    success = Column(Boolean, default=True)
    error_message = Column(String, nullable=True)

    # Index
    __table_args__ = (
        Index("ix_audit_user_action", "user_id", "action"),
        Index("ix_audit_timestamp_action", "timestamp", "action"),
    )
