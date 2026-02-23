from flask import Blueprint

upload_bp = Blueprint('upload', __name__, url_prefix='/upload')

from . import routes  # noqa: E402,F401
