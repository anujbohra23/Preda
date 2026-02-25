import json
import os
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Appointment, AppointmentAction, AuditLog, Session
from .forms import AudioUploadForm, ConsentForm, ManualNotesForm
from .summariser import extract_actions, summarise
from .transcriber import transcribe_audio, whisper_available

appointments_bp = Blueprint("appointments", __name__, url_prefix="/appointments")

ALLOWED_AUDIO = {"mp3", "wav", "m4a", "webm", "ogg"}
MAX_AUDIO_MB = 50


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return s


def _own_appointment_or_404(appt_id: int) -> Appointment:
    a = db.session.get(Appointment, appt_id)
    if a is None or a.user_id != current_user.id:
        abort(404)
    return a


def _log_audit(session_id, event, detail):
    db.session.add(
        AuditLog(
            user_id=current_user.id,
            session_id=session_id,
            event_type=event,
            event_detail=json.dumps(detail),
            created_at=_utcnow(),
        )
    )


def _audio_upload_dir(session_id: int) -> str:
    from flask import current_app

    base = current_app.config["UPLOAD_FOLDER"]
    d = os.path.join(base, "appointments", str(current_user.id), str(session_id))
    os.makedirs(d, exist_ok=True)
    return d


def _process_and_save(appt: Appointment, text: str):
    """Run summariser, save actions, update appointment record."""
    appt.status = "summarising"
    db.session.commit()

    result = summarise(text)

    if not result["success"]:
        appt.status = "failed"
        db.session.commit()
        return False, result["error"]

    summary = result["summary"]
    appt.summary_json = json.dumps(summary)
    appt.followup_date = summary.get("followup_date")
    appt.status = "done"

    # Save actions
    AppointmentAction.query.filter_by(appointment_id=appt.id).delete()

    for action_data in extract_actions(summary):
        db.session.add(
            AppointmentAction(
                appointment_id=appt.id,
                action_type=action_data["action_type"],
                description=action_data["description"],
                detail=action_data["detail"],
                due_date=action_data["due_date"],
                is_completed=0,
                created_at=_utcnow(),
            )
        )

    db.session.commit()
    return True, None


# ── List ───────────────────────────────────────────────────────────────────────


@appointments_bp.route("/session/<int:session_id>")
@login_required
def list_appointments(session_id):
    s = _own_session_or_404(session_id)
    appts = (
        Appointment.query.filter_by(session_id=session_id)
        .order_by(Appointment.created_at.desc())
        .all()
    )
    return render_template("appointments/list.html", session=s, appointments=appts)


# ── Choose capture method ──────────────────────────────────────────────────────


@appointments_bp.route("/session/<int:session_id>/new")
@login_required
def new_appointment(session_id):
    s = _own_session_or_404(session_id)
    return render_template(
        "appointments/new.html", session=s, whisper_ok=whisper_available()
    )


# ── Live recording ─────────────────────────────────────────────────────────────


@appointments_bp.route("/session/<int:session_id>/record", methods=["GET", "POST"])
@login_required
def record_appointment(session_id):
    s = _own_session_or_404(session_id)
    form = ConsentForm()

    if request.method == "GET":
        return render_template("appointments/record.html", session=s, form=form)

    # POST — receive audio blob from browser
    audio_blob = request.files.get("audio")
    doctor = request.form.get("doctor_name", "").strip()
    appt_date = request.form.get("appointment_date", "").strip()

    if not audio_blob:
        flash("No audio received. Please try again.", "error")
        return redirect(
            url_for("appointments.record_appointment", session_id=session_id)
        )

    # Save audio file
    upload_dir = _audio_upload_dir(session_id)
    filename = secure_filename(
        f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
    )
    audio_path = os.path.join(upload_dir, filename)
    audio_blob.save(audio_path)

    # Create appointment record
    appt = Appointment(
        session_id=session_id,
        user_id=current_user.id,
        title=f"Appointment — {doctor or 'Unknown Doctor'} "
        f"{appt_date or ''}".strip(),
        doctor_name=doctor,
        appointment_date=appt_date,
        capture_method="recording",
        audio_path=audio_path,
        status="transcribing",
        created_at=_utcnow(),
    )
    db.session.add(appt)
    db.session.commit()

    # Transcribe
    t_result = transcribe_audio(audio_path)
    if not t_result["success"]:
        appt.status = "failed"
        db.session.commit()
        flash(
            f"Transcription failed: {t_result['error']} "
            "You can add notes manually instead.",
            "error",
        )
        return redirect(url_for("appointments.detail", appt_id=appt.id))

    appt.raw_transcript = t_result["transcript"]
    db.session.commit()

    # Summarise
    ok, err = _process_and_save(appt, t_result["transcript"])
    if not ok:
        flash(f"Summary failed: {err}", "error")

    _log_audit(
        session_id, "appointment_created", {"appt_id": appt.id, "method": "recording"}
    )
    db.session.commit()

    return redirect(url_for("appointments.detail", appt_id=appt.id))


# ── Upload audio ───────────────────────────────────────────────────────────────


@appointments_bp.route("/session/<int:session_id>/upload", methods=["GET", "POST"])
@login_required
def upload_appointment(session_id):
    s = _own_session_or_404(session_id)
    form = AudioUploadForm()

    if form.validate_on_submit():
        audio_file = form.audio_file.data
        if not audio_file:
            flash("Please select an audio file.", "error")
            return render_template("appointments/upload.html", session=s, form=form)

        # Size check
        audio_file.seek(0, 2)
        size_mb = audio_file.tell() / (1024 * 1024)
        audio_file.seek(0)

        if size_mb > MAX_AUDIO_MB:
            flash(f"File too large. Maximum size is {MAX_AUDIO_MB}MB.", "error")
            return render_template("appointments/upload.html", session=s, form=form)

        upload_dir = _audio_upload_dir(session_id)
        filename = secure_filename(
            f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
            f"{audio_file.filename}"
        )
        audio_path = os.path.join(upload_dir, filename)
        audio_file.save(audio_path)

        doctor = (form.doctor_name.data or "").strip()
        appt_date = (form.appointment_date.data or "").strip()

        appt = Appointment(
            session_id=session_id,
            user_id=current_user.id,
            title=f"Appointment — {doctor or 'Unknown Doctor'} "
            f"{appt_date or ''}".strip(),
            doctor_name=doctor,
            appointment_date=appt_date,
            capture_method="upload",
            audio_path=audio_path,
            status="transcribing",
            created_at=_utcnow(),
        )
        db.session.add(appt)
        db.session.commit()

        t_result = transcribe_audio(audio_path)
        if not t_result["success"]:
            appt.status = "failed"
            db.session.commit()
            flash(
                f"Transcription failed: {t_result['error']} "
                "Please add notes manually.",
                "error",
            )
            return redirect(url_for("appointments.detail", appt_id=appt.id))

        appt.raw_transcript = t_result["transcript"]
        db.session.commit()

        ok, err = _process_and_save(appt, t_result["transcript"])
        if not ok:
            flash(f"Summary failed: {err}", "error")

        _log_audit(
            session_id, "appointment_created", {"appt_id": appt.id, "method": "upload"}
        )
        db.session.commit()

        return redirect(url_for("appointments.detail", appt_id=appt.id))

    return render_template("appointments/upload.html", session=s, form=form)


# ── Manual notes ───────────────────────────────────────────────────────────────


@appointments_bp.route("/session/<int:session_id>/manual", methods=["GET", "POST"])
@login_required
def manual_appointment(session_id):
    s = _own_session_or_404(session_id)
    form = ManualNotesForm()

    if form.validate_on_submit():
        doctor = (form.doctor_name.data or "").strip()
        appt_date = (form.appointment_date.data or "").strip()
        notes = form.notes.data.strip()

        appt = Appointment(
            session_id=session_id,
            user_id=current_user.id,
            title=f"Appointment — {doctor or 'Unknown Doctor'} "
            f"{appt_date or ''}".strip(),
            doctor_name=doctor,
            appointment_date=appt_date,
            capture_method="manual",
            raw_transcript=notes,
            status="summarising",
            created_at=_utcnow(),
        )
        db.session.add(appt)
        db.session.commit()

        ok, err = _process_and_save(appt, notes)
        if not ok:
            flash(f"Summary failed: {err}", "error")

        _log_audit(
            session_id, "appointment_created", {"appt_id": appt.id, "method": "manual"}
        )
        db.session.commit()

        return redirect(url_for("appointments.detail", appt_id=appt.id))

    return render_template("appointments/manual.html", session=s, form=form)


# ── Detail ─────────────────────────────────────────────────────────────────────


@appointments_bp.route("/<int:appt_id>")
@login_required
def detail(appt_id):
    appt = _own_appointment_or_404(appt_id)
    session = db.session.get(Session, appt.session_id)
    summary = {}
    if appt.summary_json:
        try:
            summary = json.loads(appt.summary_json)
        except Exception:
            pass

    actions_by_type = {}
    for a in appt.actions.order_by(AppointmentAction.action_type).all():
        actions_by_type.setdefault(a.action_type, []).append(a)

    return render_template(
        "appointments/detail.html",
        appt=appt,
        session=session,
        summary=summary,
        actions_by_type=actions_by_type,
    )


# ── Toggle action complete ─────────────────────────────────────────────────────


@appointments_bp.route("/action/<int:action_id>/toggle", methods=["POST"])
@login_required
def toggle_action(action_id):
    action = db.session.get(AppointmentAction, action_id)
    if action is None:
        abort(404)
    _own_appointment_or_404(action.appointment_id)

    action.is_completed = 0 if action.is_completed else 1
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "is_completed": action.is_completed,
        }
    )


# ── Delete ─────────────────────────────────────────────────────────────────────


@appointments_bp.route("/<int:appt_id>/delete", methods=["POST"])
@login_required
def delete_appointment(appt_id):
    appt = _own_appointment_or_404(appt_id)
    session_id = appt.session_id

    if appt.audio_path and os.path.exists(appt.audio_path):
        try:
            os.remove(appt.audio_path)
        except OSError:
            pass

    _log_audit(session_id, "appointment_deleted", {"appt_id": appt_id})
    db.session.delete(appt)
    db.session.commit()

    flash("Appointment deleted.", "success")
    return redirect(url_for("appointments.list_appointments", session_id=session_id))
