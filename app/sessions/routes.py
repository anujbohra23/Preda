import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Appointment, ChatMessage, DiseaseResult, LabValue, Session
from .forms import NewSessionForm

sessions_bp = Blueprint("sessions", __name__, url_prefix="/sessions")



def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
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

    # ── Follow-up alerts ───────────────────────────────────────────────────
    followup_alerts = (
        Appointment.query.filter_by(user_id=current_user.id)
        .filter(Appointment.followup_date.isnot(None))
        .filter(Appointment.followup_date <= str(alert_date))
        .filter(Appointment.followup_date >= str(today))
        .all()
    )

    # ── Abnormal lab values across ALL sessions ────────────────────────────
    abnormal_labs = (
        LabValue.query
        .filter_by(user_id=current_user.id)
        .filter(LabValue.status.in_(["high", "low"]))
        .filter(LabValue.value.isnot(None))
        .order_by(LabValue.created_at.desc())
        .all()
    )

    # Deduplicate — keep latest per test_name
    seen = set()
    unique_abnormal = []
    for lab in abnormal_labs:
        if lab.test_name not in seen:
            seen.add(lab.test_name)
            unique_abnormal.append(lab)

    # ── Health summary stats ───────────────────────────────────────────────
    total_sessions   = len(user_sessions)
    total_uploads    = sum(s.uploads.count() for s in user_sessions)
    total_abnormal   = len(unique_abnormal)

    # Last upload date
    last_upload_date = None
    for s in user_sessions:
        for u in s.uploads.all():
            d = u.created_at[:10] if u.created_at else None
            if d and (last_upload_date is None or d > last_upload_date):
                last_upload_date = d

    # Next follow-up
    next_followup = None
    all_appts = (
        Appointment.query.filter_by(user_id=current_user.id)
        .filter(Appointment.followup_date.isnot(None))
        .filter(Appointment.followup_date >= str(today))
        .order_by(Appointment.followup_date)
        .first()
    )
    if all_appts:
        next_followup = all_appts.followup_date

    # ── Per-session lab snapshot (top abnormal per session) ────────────────
    session_lab_snapshot = {}
    for s in user_sessions:
        top = (
            LabValue.query
            .filter_by(session_id=s.id, user_id=current_user.id)
            .filter(LabValue.status.in_(["high", "low"]))
            .filter(LabValue.value.isnot(None))
            .order_by(LabValue.created_at.desc())
            .first()
        )
        if top:
            session_lab_snapshot[s.id] = top

    # ── Recent activity feed (last 8 events across all sessions) ──────────
    activity = []
    for s in user_sessions[:5]:
        # Latest chat message
        last_msg = (
            ChatMessage.query.filter_by(session_id=s.id)
            .order_by(ChatMessage.created_at.desc())
            .first()
        )
        if last_msg:
            activity.append({
                "type":       "chat",
                "session":    s,
                "date":       last_msg.created_at[:10],
                "detail": f'Chat in "{s.title}"',
            })

        # Lab extraction
        lab_count = LabValue.query.filter_by(
            session_id=s.id, user_id=current_user.id
        ).count()
        if lab_count:
            abnormal_count = LabValue.query.filter_by(
                session_id=s.id, user_id=current_user.id
            ).filter(LabValue.status.in_(["high", "low"])).count()
            activity.append({
                "type":   "lab",
                "session": s,
                "date":   s.updated_at[:10] if s.updated_at else s.created_at[:10],
                "detail": f"{lab_count} lab values extracted"
                          + (f", {abnormal_count} abnormal" if abnormal_count else ""),
            })

    # Sort by date desc, cap at 6
    activity.sort(key=lambda x: x["date"], reverse=True)
    activity = activity[:6]

    return render_template(
        "sessions/dashboard.html",
        sessions=user_sessions,
        form=form,
        followup_alerts=followup_alerts,
        # Stats
        total_sessions=total_sessions,
        total_uploads=total_uploads,
        total_abnormal=total_abnormal,
        last_upload_date=last_upload_date,
        next_followup=next_followup,
        # Abnormal labs panel
        unique_abnormal=unique_abnormal[:6],
        # Per-session lab snapshot
        session_lab_snapshot=session_lab_snapshot,
        # Activity feed
        activity=activity,
        # Greeting
        now_hour=datetime.now(timezone.utc).hour,
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

    intake   = {f.field_name: f.field_value for f in s.intake_fields.all()}
    uploads  = s.uploads.all()
    diseases = s.disease_results.order_by(DiseaseResult.rank).all()
    messages = s.chat_messages.order_by(ChatMessage.created_at).all()
    reports  = s.reports.all()
    labs     = (
        LabValue.query
        .filter_by(session_id=session_id, user_id=current_user.id)
        .filter(LabValue.value.isnot(None))
        .order_by(LabValue.test_name)
        .all()
    )

    return render_template(
        "sessions/detail.html",
        s=s,
        intake=intake,
        uploads=uploads,
        diseases=diseases,
        messages=messages,
        reports=reports,
        labs=labs,
    )


# ── Delete session ─────────────────────────────────────────────────────────────


@sessions_bp.route("/<int:session_id>/delete", methods=["POST"])
@login_required
def delete_session(session_id):
    s = _own_session_or_404(session_id)
    title = s.title

    for upload in s.uploads.all():
        if upload.stored_path and os.path.exists(upload.stored_path):
            os.remove(upload.stored_path)

    db.session.delete(s)
    db.session.commit()
    flash(f'Session "{title}" deleted.', "success")
    return redirect(url_for("sessions.dashboard"))