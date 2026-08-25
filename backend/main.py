"""FastAPI application factory: middleware, lifecycle hooks, and router wiring."""
import logging

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from utils import config
from services import storage as store
from models.database import close_client
from routers import account, admin, appointments, auth, coach, dermatologists, files, payments, profile, sessions, timeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DOMAIN_ROUTERS = (
    auth.router,
    profile.router,
    sessions.router,
    timeline.router,
    files.router,
    account.router,
    dermatologists.router,
    admin.router,
    appointments.router,
    coach.router,
    payments.router,
)


def create_app() -> FastAPI:
    app = FastAPI(title="ReHairAnalytics API")

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/health")
    async def api_health():
        return {"status": "healthy"}

    api_router = APIRouter(prefix="/api")

    @api_router.get("/")
    async def root():
        return {"message": "ReHairAnalytics API", "status": "ok"}

    for domain_router in DOMAIN_ROUTERS:
        api_router.include_router(domain_router)
    app.include_router(api_router)

    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup() -> None:
        if config.CORS_ORIGINS == ["*"]:
            # allow_credentials=True + a wildcard origin means the browser's own
            # CORS rules force this middleware to reflect whatever Origin the
            # request sent -- i.e. ANY site can make credentialed requests using
            # a visitor's session cookie. Fine for local dev; never for prod.
            logger.warning(
                "CORS_ORIGINS is not set (defaulting to '*') -- combined with "
                "allow_credentials=True this lets any origin make authenticated "
                "requests using a visitor's session cookie. Set CORS_ORIGINS to "
                "the real frontend origin(s) before going to production."
            )
        try:
            store.init_storage()
            logger.info("Storage initialized")
        except Exception as e:
            logger.error(f"Storage init failed: {e}")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        close_client()

    return app


app = create_app()
