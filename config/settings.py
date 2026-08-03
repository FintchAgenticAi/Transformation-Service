import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")
APP_NAME     = os.getenv("APP_NAME", "AI Financial Platform")
VERSION      = os.getenv("VERSION", "1.0.0")
