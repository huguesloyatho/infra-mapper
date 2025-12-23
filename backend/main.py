"""Point d'entrée du backend Infra-Mapper."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import get_settings
from middleware import SecurityHeadersMiddleware, limiter, rate_limit_exceeded_handler, MetricsMiddleware
from db import init_db
from db.database import get_db_session
from api import router
from api.auth_routes import router as auth_router
from api.user_routes import router as user_router
from api.idp_routes import router as idp_router
from api.audit_routes import router as audit_router
from api.alert_routes import router as alert_router
from api.backup_routes import router as backup_router
from api.metrics_routes import router as metrics_router
from api.log_sink_routes import router as log_sink_router
from api.agent_health_routes import router as agent_health_router
from api.container_actions_routes import router as container_actions_router
from api.export_routes import router as export_router
from api.report_routes import router as report_router
from api.organization_routes import router as organization_router

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("infra-mapper")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle de l'application."""
    # Startup
    logger.info("Démarrage d'Infra-Mapper...")
    await init_db()
    logger.info("Base de données initialisée")

    # Créer l'admin initial si configuré
    if settings.auth_enabled and settings.initial_admin_password:
        try:
            from services.user_service import create_initial_admin
            async with get_db_session() as db:
                await create_initial_admin(db)
        except Exception as e:
            logger.error(f"Erreur création admin initial: {e}")

    if settings.auth_enabled:
        logger.info("Authentification activée")
    else:
        logger.info("Authentification désactivée (AUTH_ENABLED=false)")

    yield
    # Shutdown
    logger.info("Arrêt d'Infra-Mapper")


# Création de l'application
app = FastAPI(
    title=settings.app_name,
    description="Solution de cartographie dynamique d'infrastructure Docker",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Metrics middleware (doit être avant les autres pour mesurer le temps total)
app.add_middleware(MetricsMiddleware)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Trusted hosts middleware (for reverse proxy)
if settings.trusted_hosts and settings.trusted_hosts != ["*"]:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts
    )

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes API
app.include_router(router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(idp_router)
app.include_router(audit_router)
app.include_router(alert_router)
app.include_router(backup_router)
app.include_router(metrics_router)
app.include_router(log_sink_router)
app.include_router(agent_health_router)
app.include_router(container_actions_router)
app.include_router(export_router)
app.include_router(report_router)
app.include_router(organization_router)

# Servir le frontend en production
# app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
