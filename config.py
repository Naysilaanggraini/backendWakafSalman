import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy import URL

load_dotenv()


def load_config():
    production = os.getenv("APP_ENV", "development") == "production"
    origins = [item.strip() for item in os.getenv(
        "CORS_ORIGINS", "" if production else "http://localhost:5173").split(",") if item.strip()]
    secret = os.getenv("JWT_SECRET_KEY", "")
    password = os.getenv("DB_PASSWORD", "")
    if production:
        if len(secret) < 32 or secret.startswith("CHANGE_ME"):
            raise ValueError("Production requires a random JWT_SECRET_KEY of at least 32 characters")
        if not password or password.startswith("CHANGE_ME"):
            raise ValueError("Production requires DB_PASSWORD")
        if not origins or any(urlsplit(origin).scheme != "https" or not urlsplit(origin).netloc
                              or "*" in origin or urlsplit(origin).path not in ("", "/")
                              for origin in origins):
            raise ValueError("Production CORS_ORIGINS must contain explicit HTTPS origins")
    config = {
        "APP_ENV": "production" if production else "development",
        "SQLALCHEMY_DATABASE_URI": URL.create(
            "mysql+pymysql", username=os.getenv("DB_USER", "lentera"), password=password,
            host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME", "lentera"), query={"charset": "utf8mb4"}),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "pool_pre_ping": True, "pool_recycle": 300,
            "connect_args": {"connect_timeout": 5},
        },
        "JWT_SECRET_KEY": secret,
        "CORS_ORIGINS": origins,
        "MAX_CONTENT_LENGTH": 3 * 1024 * 1024,
        "ENABLE_DEV_ROUTES": not production and os.getenv("ENABLE_DEV_ROUTES", "false").lower() == "true",
        "PROXY_HOPS": int(os.getenv("PROXY_HOPS", "0")),
        "DEBUG": not production and os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true"),
    }
    if os.getenv("PROFILE_PHOTO_DIR"):
        config["PROFILE_PHOTO_DIR"] = str(Path(os.environ["PROFILE_PHOTO_DIR"]).resolve())
    return config
