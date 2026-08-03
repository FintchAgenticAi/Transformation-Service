
import logging
import time

from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

from config.settings import APP_NAME, VERSION
from config.database import engine, Base
from routes.health import router as health_router
from routes.transformation_rules import router as transformation_rules_router

# Import models so Base.metadata.create_all registers all tables
from models import transformation_rules  # noqa: F401

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=APP_NAME,
    version=VERSION,
    description="Transformation Rules Service — Silver Zone catalog + execution",
)


def _create_tables(retries: int = 4, delay_seconds: float = 3.0) -> None:
    """
    Create tables with retries.

    Neon often returns 'Connection refused' while the compute is waking up.
    Do not crash the whole API process on a temporary blip.
    """
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables ready (attempt %s)", attempt)
            return
        except OperationalError as e:
            last_error = e
            logger.warning(
                "create_all failed (attempt %s/%s): %s",
                attempt,
                retries,
                e,
            )
            if attempt < retries:
                time.sleep(delay_seconds)

    logger.error(
        "Could not create tables after %s attempts. "
        "API will start, but DB routes may fail until Neon is reachable. Last error: %s",
        retries,
        last_error,
    )


_create_tables()

# Register our routes
app.include_router(health_router, tags=["Health"])
app.include_router(transformation_rules_router)
