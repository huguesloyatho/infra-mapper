"""Configuration du backend Infra-Mapper."""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Configuration du backend."""

    # Application
    app_name: str = "Infra-Mapper"
    debug: bool = False
    api_key: str = Field(default="change-me-in-production")

    # Base de données
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="infra_mapper")
    db_user: str = Field(default="postgres")
    db_password: str = Field(default="postgres")

    # === Authentication ===
    auth_enabled: bool = Field(default=False)  # Activer/désactiver l'auth utilisateur

    # JWT
    secret_key: str = Field(default="change-me-in-production-secret-key")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60  # 1 heure
    refresh_token_expire_days: int = 7

    # Sessions
    max_sessions_per_user: int = 5

    # Password policy
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = False

    # Account security
    max_failed_login_attempts: int = 5
    lockout_duration_minutes: int = 15

    # SSO
    oidc_enabled: bool = True
    saml_enabled: bool = True

    # Initial admin (créé au démarrage si password non vide)
    initial_admin_username: str = Field(default="admin")
    initial_admin_password: str = Field(default="")  # Vide = pas de création
    initial_admin_email: str = Field(default="admin@localhost")

    # Audit
    audit_log_retention_days: int = 90

    # CORS
    cors_origins: list[str] = Field(default=["*"])

    # Security headers
    security_headers_enabled: bool = Field(default=True)
    csp_policy: str = Field(default="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'self'")
    x_frame_options: str = Field(default="SAMEORIGIN")

    # Rate limiting
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_requests: int = Field(default=100)  # requests per window
    rate_limit_window: int = Field(default=60)  # window in seconds

    # Trusted proxies (for reverse proxy setups)
    trusted_hosts: list[str] = Field(default=["*"])
    forwarded_allow_ips: str = Field(default="*")

    # WebSocket
    ws_heartbeat_interval: int = 30

    # Webhook n8n (optionnel)
    n8n_webhook_url: str | None = None

    # SSH Configuration pour déploiement agents
    ssh_key_path: str = Field(default="/root/.ssh/id_rsa")
    backend_url: str = Field(default="http://localhost:8000")

    # Logs containers
    logs_retention_days: int = Field(default=7)
    logs_max_per_container: int = Field(default=10000)
    collect_container_logs: bool = Field(default=True)

    @property
    def database_url(self) -> str:
        """Retourne l'URL de connexion PostgreSQL."""
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def database_url_sync(self) -> str:
        """Retourne l'URL de connexion PostgreSQL synchrone (pour Alembic)."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_prefix = "MAPPER_"
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    """Retourne la configuration (cached)."""
    return Settings()
