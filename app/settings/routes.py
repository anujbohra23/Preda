import json
import os
from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, logout_user

from ..email.mailer import is_configured
from ..extensions import db
from ..models import (
    AuditLog,
    ChatMessage,
    DiseaseResult,
    ExtractedChunk,
    IntakeField,
    RagRetrieval,
    Report,
    Session,
    Upload,
    User,
)
from .forms import PharmacySettingsForm

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def get_pharmacy_settings(user_id: int) -> dict:
    row = (
        AuditLog.query.filter_by(user_id=user_id, event_type="pharmacy_settings_saved")
        .order_by(AuditLog.id.desc())
        .first()
    )
    if row:
        try:
            return json.loads(row.event_detail)
        except Exception:
            pass
    return {
        "pharmacy_name": "",
        "pharmacy_email": "",
        "pharmacy_address": "",
    }


@settings_bp.route("/", methods=["GET", "POST"])
@login_required
def settings():
    form = PharmacySettingsForm()
    current = get_pharmacy_settings(current_user.id)

    if form.validate_on_submit():
        detail = {
            "pharmacy_name": (form.pharmacy_name.data or "").strip(),
            "pharmacy_email": (form.pharmacy_email.data or "").strip(),
            "pharmacy_address": (form.pharmacy_address.data or "").strip(),
        }
        db.session.add(
            AuditLog(
                user_id=current_user.id,
                session_id=None,
                event_type="pharmacy_settings_saved",
                event_detail=json.dumps(detail),
                created_at=_utcnow(),
            )
        )
        db.session.commit()
        flash("Pharmacy details saved.", "success")
        return redirect(url_for("settings.settings"))

    if request.method == "GET":
        form.pharmacy_name.data = current.get("pharmacy_name", "")
        form.pharmacy_email.data = current.get("pharmacy_email", "")
        form.pharmacy_address.data = current.get("pharmacy_address", "")

    return render_template(
        "settings/settings.html",
        form=form,
        current=current,
        smtp_configured=is_configured(),
    )


@settings_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    """
    Hard delete all user data and the account itself.
    Removes uploaded files from disk too.
    """
    user_id = current_user.id

    # ── Remove files from disk ─────────────────────────────────────────────
    uploads = Upload.query.filter_by(user_id=user_id).all()
    for upload in uploads:
        if upload.stored_path and os.path.exists(upload.stored_path):
            try:
                os.remove(upload.stored_path)
            except OSError:
                pass

    # Remove report PDFs
    sessions = Session.query.filter_by(user_id=user_id).all()
    for s in sessions:
        reports = Report.query.filter_by(session_id=s.id).all()
        for r in reports:
            if r.pdf_path and os.path.exists(r.pdf_path):
                try:
                    os.remove(r.pdf_path)
                except OSError:
                    pass

    # ── Delete all DB records (cascades handle children) ──────────────────
    AuditLog.query.filter_by(user_id=user_id).delete()

    for s in sessions:
        # Children first (no cascade configured for all)
        msg_ids = [m.id for m in ChatMessage.query.filter_by(session_id=s.id).all()]
        if msg_ids:
            RagRetrieval.query.filter(RagRetrieval.chat_message_id.in_(msg_ids)).delete(
                synchronize_session=False
            )

        ChatMessage.query.filter_by(session_id=s.id).delete()
        Report.query.filter_by(session_id=s.id).delete()
        DiseaseResult.query.filter_by(session_id=s.id).delete()

        ExtractedChunk.query.filter_by(session_id=s.id).delete()
        Upload.query.filter_by(session_id=s.id).delete()
        IntakeField.query.filter_by(session_id=s.id).delete()

    Session.query.filter_by(user_id=user_id).delete()

    # ── Delete user ────────────────────────────────────────────────────────
    user = db.session.get(User, user_id)
    logout_user()
    db.session.delete(user)
    db.session.commit()

    flash(
        "Your account and all associated data have been permanently deleted.",
        "success",
    )
    return redirect(url_for("main.landing"))
