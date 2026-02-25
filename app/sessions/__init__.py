from flask import Blueprint

sessions_bp = Blueprint("sessions", __name__, url_prefix="/sessions")

from . import routes  # noqa: E402,F401
