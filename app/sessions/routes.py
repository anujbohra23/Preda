from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Appointment, ChatMessage, DiseaseResult, Session
from .forms import NewSessionForm

sessions_bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
    """Return the session if it belongs to current_user, else 404."""
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return s


# ── Dashboard ──────────────────────────────────────────────────────────────────


@sessions_bp.route("/")
@login_required
def dashboard():
    user_sessions = (
        Session.query.filter_by(user_id=current_user.id)
        .order_by(Session.created_at.desc())
        .all()
    )
    form = NewSessionForm()
    today = datetime.now(timezone.utc).date()
    alert_date = today + timedelta(days=7)

    followup_alerts = (
        Appointment.query.filter_by(user_id=current_user.id)
        .filter(Appointment.followup_date.isnot(None))
        .filter(Appointment.followup_date <= str(alert_date))
        .filter(Appointment.followup_date >= str(today))
        .all()
    )

    return render_template(
        "sessions/dashboard.html",
        sessions=user_sessions,
        form=form,
        followup_alerts=followup_alerts,
    )


# ── Create new session ─────────────────────────────────────────────────────────


@sessions_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_session():
    form = NewSessionForm()
    if form.validate_on_submit():
        title = form.title.data.strip() if form.title.data else None
        if not title:
            title = f"Session {datetime.now(timezone.utc).strftime('%b %d, %Y')}"

        s = Session(
            user_id=current_user.id,
            title=title,
            status="intake",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.session.add(s)
        db.session.commit()
        flash(f'Session "{s.title}" created.', "success")
        return redirect(url_for("intake.intake_form", session_id=s.id))

    return render_template("sessions/new_session.html", form=form)


# ── Session detail ─────────────────────────────────────────────────────────────


@sessions_bp.route("/<int:session_id>")
@login_required
def detail(session_id):
    s = _own_session_or_404(session_id)

    intake = {f.field_name: f.field_value for f in s.intake_fields.all()}
    uploads = s.uploads.all()
    diseases = s.disease_results.order_by(DiseaseResult.rank).all()
    messages = s.chat_messages.order_by(ChatMessage.created_at).all()
    reports = s.reports.all()

    return render_template(
        "sessions/detail.html",
        s=s,
        intake=intake,
        uploads=uploads,
        diseases=diseases,
        messages=messages,
        reports=reports,
    )


# ── Delete session ─────────────────────────────────────────────────────────────


@sessions_bp.route("/<int:session_id>/delete", methods=["POST"])
@login_required
def delete_session(session_id):
    s = _own_session_or_404(session_id)
    title = s.title

    # Remove uploaded files from disk
    import os

    for upload in s.uploads.all():
        if upload.stored_path and os.path.exists(upload.stored_path):
            os.remove(upload.stored_path)

    db.session.delete(s)
    db.session.commit()
    flash(f'Session "{title}" deleted.', "success")
    return redirect(url_for("sessions.dashboard"))
