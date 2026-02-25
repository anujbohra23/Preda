import json
import os
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from ..extensions import db
from ..models import AuditLog, ChatMessage, DiseaseResult, RagRetrieval, Report, Session
from .generator import (
    build_patient_report,
    build_pharmacy_report,
    render_report_pdf,
    save_pdf,
)

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return s


def _own_report_or_404(report_id: int) -> Report:
    r = db.session.get(Report, report_id)
    if r is None:
        abort(404)
    s = db.session.get(Session, r.session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return r


def _gather_session_data(s: Session) -> dict:
    """Gather all data needed to build any report type."""
    intake = {f.field_name: f.field_value or "" for f in s.intake_fields.all()}
    diseases = (
        DiseaseResult.query.filter_by(session_id=s.id)
        .order_by(DiseaseResult.rank)
        .all()
    )
    chat_messages = (
        ChatMessage.query.filter_by(session_id=s.id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    # Get all RAG retrievals for this session's messages
    msg_ids = [m.id for m in chat_messages]
    retrievals = []
    if msg_ids:
        retrievals = RagRetrieval.query.filter(
            RagRetrieval.chat_message_id.in_(msg_ids)
        ).all()
    return {
        "intake": intake,
        "diseases": diseases,
        "chat_messages": chat_messages,
        "retrievals": retrievals,
    }


def _log_audit(user_id, session_id, event, detail):
    db.session.add(
        AuditLog(
            user_id=user_id,
            session_id=session_id,
            event_type=event,
            event_detail=json.dumps(detail),
            created_at=_utcnow(),
        )
    )


# ── Report page ────────────────────────────────────────────────────────────────


@reports_bp.route("/<int:session_id>")
@login_required
def report_page(session_id):
    s = _own_session_or_404(session_id)
    data = _gather_session_data(s)

    patient_report = (
        Report.query.filter_by(session_id=session_id, report_type="patient")
        .order_by(Report.generated_at.desc())
        .first()
    )

    pharmacy_report = (
        Report.query.filter_by(session_id=session_id, report_type="pharmacy")
        .order_by(Report.generated_at.desc())
        .first()
    )

    # Update session status
    if s.status not in ("report",):
        s.status = "report"
        s.updated_at = _utcnow()
        db.session.commit()

    return render_template(
        "reports/report.html",
        session=s,
        intake=data["intake"],
        diseases=data["diseases"][:5],
        patient_report=patient_report,
        pharmacy_report=pharmacy_report,
        has_diseases=len(data["diseases"]) > 0,
        has_chat=len(data["chat_messages"]) > 0,
    )


# ── Generate report ────────────────────────────────────────────────────────────


@reports_bp.route("/<int:session_id>/generate", methods=["POST"])
@login_required
def generate_report(session_id):
    s = _own_session_or_404(session_id)
    report_type = request.form.get("report_type", "patient")

    if report_type not in ("patient", "pharmacy"):
        flash("Invalid report type.", "error")
        return redirect(url_for("reports.report_page", session_id=session_id))

    if s.safety_flagged and report_type == "pharmacy":
        flash(
            "Pharmacy report is disabled for this session "
            "because a safety alert was triggered.",
            "error",
        )
        return redirect(url_for("reports.report_page", session_id=session_id))

    data = _gather_session_data(s)

    if not data["diseases"]:
        flash(
            "Please complete condition matching before generating a report.", "warning"
        )
        return redirect(url_for("retrieve.results", session_id=session_id))

    # ── Build report context ───────────────────────────────────────────────
    if report_type == "patient":
        context = build_patient_report(
            s,
            data["intake"],
            data["diseases"],
            data["chat_messages"],
            data["retrievals"],
        )
    else:
        context = build_pharmacy_report(
            s,
            data["intake"],
            data["diseases"],
            data["chat_messages"],
            data["retrievals"],
        )

    # ── Render PDF ─────────────────────────────────────────────────────────
    try:
        pdf_bytes = render_report_pdf(report_type, context)
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        stored_path = save_pdf(pdf_bytes, session_id, report_type, upload_folder)
    except Exception as e:
        flash(f"PDF generation failed: {e}", "error")
        return redirect(url_for("reports.report_page", session_id=session_id))

    # ── Save to DB ─────────────────────────────────────────────────────────
    report = Report(
        session_id=session_id,
        report_type=report_type,
        content_json=json.dumps(context),
        pdf_path=stored_path,
        generated_at=_utcnow(),
    )
    db.session.add(report)
    _log_audit(
        current_user.id,
        session_id,
        "report_generated",
        {
            "report_type": report_type,
        },
    )
    db.session.commit()

    flash(f"{report_type.capitalize()} report generated successfully.", "success")
    return redirect(url_for("reports.report_page", session_id=session_id))


# ── Download PDF ───────────────────────────────────────────────────────────────


@reports_bp.route("/download/<int:report_id>")
@login_required
def download_report(report_id):
    report = _own_report_or_404(report_id)

    if not report.pdf_path or not os.path.exists(report.pdf_path):
        flash("PDF file not found. Please regenerate the report.", "error")
        return redirect(url_for("reports.report_page", session_id=report.session_id))

    _log_audit(
        current_user.id,
        report.session_id,
        "pdf_exported",
        {
            "report_id": report.id,
            "report_type": report.report_type,
        },
    )
    db.session.commit()

    filename = f"healthassist_{report.report_type}_report.pdf"
    return send_file(
        report.pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
