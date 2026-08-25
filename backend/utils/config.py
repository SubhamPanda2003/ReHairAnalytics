"""Environment-derived settings and app-wide constants."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
SUPER_ADMIN_EMAIL = (os.environ.get("SUPER_ADMIN_EMAIL") or "").strip().lower()

RAZORPAY_KEY_ID = os.environ["RAZORPAY_KEY_ID"]
RAZORPAY_KEY_SECRET = os.environ["RAZORPAY_KEY_SECRET"]

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
SESSION_TTL_DAYS = 7

MAX_UPLOAD_SIZE = 10 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
MANUAL_VIEWS = {"front", "left", "right", "top", "back"}
MIN_ACCEPTABLE_QUALITY = 60
