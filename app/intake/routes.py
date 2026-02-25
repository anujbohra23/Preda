from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from ..extensions import db
from ..models import ExtractedChunk, IntakeField, Session, Upload
from ..upload.extractor import extract_and_chunk, save_upload
from .forms import IntakeForm

intake_bp = Blueprint("intake", __name__, url_prefix="/intake")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return s


def _upsert_intake_field(session_id: int, field_name: str, field_value: str):
    """Insert or update a single intake field row."""
    existing = IntakeField.query.filter_by(
        session_id=session_id, field_name=field_name
    ).first()
    if existing:
        existing.field_value = field_value
    else:
        db.session.add(
            IntakeField(
                session_id=session_id,
                field_name=field_name,
                field_value=field_value,
                created_at=_utcnow(),
            )
        )


# ── Intake form ────────────────────────────────────────────────────────────────


@intake_bp.route("/<int:session_id>", methods=["GET", "POST"])
@login_required
def intake_form(session_id):
    s = _own_session_or_404(session_id)
    form = IntakeForm()

    # Pre-populate form from existing intake_fields on GET
    if request.method == "GET":
        existing = {f.field_name: f.field_value for f in s.intake_fields.all()}
        form.age.data = int(existing["age"]) if existing.get("age") else None
        form.sex.data = existing.get("sex", "")
        form.chief_complaint.data = existing.get("chief_complaint", "")
        form.duration.data = existing.get("duration", "")
        form.medications.data = existing.get("medications", "")
        form.allergies.data = existing.get("allergies", "")
        form.additional_notes.data = existing.get("additional_notes", "")

    if form.validate_on_submit():
        fields = {
            "age": str(form.age.data),
            "sex": form.sex.data,
            "chief_complaint": form.chief_complaint.data.strip(),
            "duration": form.duration.data.strip(),
            "medications": (form.medications.data or "").strip(),
            "allergies": (form.allergies.data or "").strip(),
            "additional_notes": (form.additional_notes.data or "").strip(),
        }
        for name, value in fields.items():
            _upsert_intake_field(session_id, name, value)

        # ── Safety check on intake ─────────────────────────────────────────
        from ..safety.triage import check_intake_safety

        safety = check_intake_safety(fields)
        if safety["triggered"]:
            s.safety_flagged = 1
            flash(
                f"🚨 {safety['emergency_message']} "
                "If this is an emergency, call 911 / 999 / 112 immediately.",
                "emergency",
            )

        # ... rest of the PDF upload logic unchanged ...

        # ── Handle PDF upload ──────────────────────────────────────────────
        pdf = form.pdf_file.data
        upload_obj = None

        if pdf and pdf.filename:
            try:
                upload_folder = current_app.config["UPLOAD_FOLDER"]
                file_info = save_upload(pdf, upload_folder, current_user.id, session_id)

                upload_obj = Upload(
                    session_id=session_id,
                    user_id=current_user.id,
                    original_name=file_info["original_name"],
                    stored_path=file_info["stored_path"],
                    file_size_bytes=file_info["file_size_bytes"],
                    mime_type=file_info["mime_type"],
                    upload_status="pending",
                    created_at=_utcnow(),
                )
                db.session.add(upload_obj)
                db.session.flush()  # get upload_obj.id before commit

                # ── Extract and chunk ──────────────────────────────────────
                chunks = extract_and_chunk(file_info["stored_path"])

                if chunks:
                    for i, chunk_text in enumerate(chunks):
                        db.session.add(
                            ExtractedChunk(
                                upload_id=upload_obj.id,
                                session_id=session_id,
                                chunk_index=i,
                                chunk_text=chunk_text,
                                is_confirmed=0,
                                created_at=_utcnow(),
                            )
                        )
                    upload_obj.upload_status = "extracted"
                    s.status = "reviewing"
                    flash(
                        f"PDF uploaded and {len(chunks)} text chunks extracted. "
                        f"Please review the extracted text below.",
                        "success",
                    )
                else:
                    upload_obj.upload_status = "failed"
                    flash(
                        "PDF uploaded but no text could be extracted. "
                        "The file may be a scanned image. "
                        "Your intake data has been saved.",
                        "warning",
                    )
                    s.status = "results"

            except ValueError as e:
                flash(str(e), "error")
                db.session.rollback()
                return render_template("intake/intake.html", form=form, session=s)

        else:
            # No PDF — go straight to retrieval
            if s.status == "intake":
                s.status = "results"

        s.updated_at = _utcnow()
        db.session.commit()

        if upload_obj and upload_obj.upload_status == "extracted":
            return redirect(url_for("upload.review", session_id=session_id))
        else:
            flash("Intake saved.", "success")
            return redirect(url_for("retrieve.results", session_id=session_id))

    return render_template("intake/intake.html", form=form, session=s)
