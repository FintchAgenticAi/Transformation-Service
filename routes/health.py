
from fastapi import APIRouter
from config.database import check_connection
from config.settings import APP_NAME, VERSION

router = APIRouter()

@router.get("/")
def home():
    return {
        "app":     APP_NAME,
        "version": VERSION,
        "status":  "running"
    }

@router.get("/health")
def health_check():
    db_status = check_connection()
    return {
        "status":   "healthy" if db_status else "unhealthy",
        "database": "connected" if db_status else "disconnected"
    }
    