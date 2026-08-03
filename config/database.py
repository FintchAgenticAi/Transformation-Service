import logging
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError
from config.settings import DATABASE_URL

logger = logging.getLogger(__name__)

# Neon / remote Postgres: short connect timeout + recycle stale connections
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=280,
    pool_size=5,
    max_overflow=5,
    connect_args={
        "connect_timeout": 15,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    },
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection(retries: int = 3, delay_seconds: float = 2.0) -> bool:
    """Try connecting a few times (helps with temporary Neon/network blips)."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            logger.info("Database connection successful (attempt %s)", attempt)
            return True
        except OperationalError as e:
            last_error = e
            logger.warning(
                "Database connection failed (attempt %s/%s): %s",
                attempt,
                retries,
                e,
            )
            if attempt < retries:
                time.sleep(delay_seconds)
        except Exception as e:
            last_error = e
            logger.error("Database connection failed: %s", e)
            break

    logger.error("Database connection failed after retries: %s", last_error)
    return False


def session_with_retry(retries: int = 3, delay_seconds: float = 2.0):
    """
    Open a DB session after verifying connectivity.
    Use in scripts (seed/tests) to survive temporary connection refused errors.
    """
    if not check_connection(retries=retries, delay_seconds=delay_seconds):
        raise RuntimeError(
            "Could not connect to database after retries. "
            "Check internet / Neon project status / DATABASE_URL."
        )
    return SessionLocal()
