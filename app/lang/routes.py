"""
app/lang/routes.py

Language switching — stores preference in Flask session only.
Lost on logout by design.
"""
from flask import Blueprint, redirect, request, session

lang_bp = Blueprint("lang", __name__, url_prefix="/lang")

SUPPORTED = {"en", "hi"}


@lang_bp.route("/set/<code>")
def set_language(code):
    if code not in SUPPORTED:
        code = "en"

    session["lang"] = code
    session.permanent = True  # survives browser close

    referrer = request.referrer or "/"
    return redirect(referrer)
