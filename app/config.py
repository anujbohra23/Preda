import os


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), "uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    WTF_CSRF_ENABLED = True
    WTF_CSRF_HEADERS = ["X-CSRFToken"]

    # ── Database ───────────────────────────────────────────────────────────
    # Prefer DATABASE_URL from environment (Postgres on Railway/Render/Docker)
    # Fall back to SQLite for local dev without Docker
    _db_url = os.environ.get("DATABASE_URL", "")

    # Railway provides postgres:// but SQLAlchemy needs postgresql://
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = _db_url or "sqlite:///health.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,  # reconnect on stale connections
        "pool_recycle": 300,  # recycle connections every 5 min
    }


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False

    # Enforce strong secret key in production
    @classmethod
    def init_app(cls, app):
        secret = os.environ.get("SECRET_KEY", "")
        if not secret or secret == "dev-secret-change-in-prod":
            raise ValueError(
                "SECRET_KEY must be set to a strong random value in production."
            )


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
