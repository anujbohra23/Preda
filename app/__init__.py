import os

from flask import Flask, session

from .appointments.routes import appointments_bp
from .config import DevelopmentConfig, config_map
from .extensions import babel, csrf, db, limiter, login_manager, migrate


def create_app(config_name: str = None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    cfg = config_map.get(config_name, DevelopmentConfig)
    app.config.from_object(cfg)
    app.register_blueprint(appointments_bp)

    app.config["WTF_CSRF_HEADERS"] = ["X-CSRFToken"]

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ── Language / Babel ─────────────────────────────────────────────────────
    def get_locale():
        lang = session.get("lang", "en")
        return lang if lang in ("en", "hi") else "en"

    babel.init_app(app, locale_selector=get_locale)

    from .lang.routes import lang_bp

    app.register_blueprint(lang_bp)

    @app.context_processor
    def inject_globals():
        lang = session.get("lang", "en")
        return {
            "current_lang": lang,
            "is_hindi": lang == "hi",
        }

    # ── Feature blueprints ───────────────────────────────────────────────────
    from .auth.routes import auth_bp
    from .email.routes import email_bp
    from .history.routes import history_bp
    from .intake.routes import intake_bp
    from .main.routes import main_bp
    from .rag.routes import chat_bp
    from .reports.routes import reports_bp
    from .retrieve.routes import retrieve_bp
    from .sessions.routes import sessions_bp
    from .settings.routes import settings_bp
    from .upload.routes import upload_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(intake_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(retrieve_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(email_bp)

    return app
