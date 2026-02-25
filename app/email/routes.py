import json
from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..email.forms import EmailConsentForm
from ..email.mailer import is_configured, send_pharmacy_report
from ..extensions import db
from ..models import AuditLog, Report, Session
from ..settings.routes import get_pharmacy_settings

email_bp = Blueprint("email", __name__, url_prefix="/email")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_report_or_404(report_id: int) -> Report:
    from flask import abort

    r = db.session.get(Report, report_id)
    if r is None:
        abort(404)
    s = db.session.get(Session, r.session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return r


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


@email_bp.route("/<int:report_id>/consent", methods=["GET", "POST"])
@login_required
def consent_page(report_id):
    report = _own_report_or_404(report_id)
    session = db.session.get(Session, report.session_id)
    pharmacy = get_pharmacy_settings(current_user.id)
    form = EmailConsentForm()

    if report.report_type != "pharmacy":
        flash("Only pharmacy reports can be emailed.", "error")
        return redirect(url_for("reports.report_page", session_id=report.session_id))

    if session.safety_flagged:
        flash("Email sharing is disabled for sessions with safety alerts.", "error")
        return redirect(url_for("reports.report_page", session_id=report.session_id))

    # Guard: no pharmacy saved yet
    if not pharmacy.get("pharmacy_email"):
        flash("Please save your pharmacy details in Settings first.", "warning")
        return redirect(url_for("settings.settings"))

    smtp_available = is_configured()

    if form.validate_on_submit():
        # Log consent before sending
        _log_audit(
            current_user.id,
            report.session_id,
            "email_consent_given",
            {
                "report_id": report.id,
                "recipient_email": pharmacy["pharmacy_email"],
                "recipient_name": pharmacy["pharmacy_name"],
                "consent_note": form.consent_note.data,
            },
        )
        db.session.commit()

        result = send_pharmacy_report(
            recipient_email=pharmacy["pharmacy_email"],
            recipient_name=pharmacy["pharmacy_name"],
            sender_name=current_user.email,
            pdf_path=report.pdf_path,
            session_title=session.title,
            consent_note=form.consent_note.data.strip(),
        )

        if result["success"]:
            _log_audit(
                current_user.id,
                report.session_id,
                "email_sent",
                {
                    "report_id": report.id,
                    "recipient_email": pharmacy["pharmacy_email"],
                },
            )
            db.session.commit()
            return render_template(
                "email/email_sent.html",
                session=session,
                recipient_name=pharmacy["pharmacy_name"],
                recipient_email=pharmacy["pharmacy_email"],
            )
        else:
            _log_audit(
                current_user.id,
                report.session_id,
                "email_failed",
                {
                    "report_id": report.id,
                    "error": result["error"],
                },
            )
            db.session.commit()
            flash(f"Email failed: {result['error']}", "error")

    return render_template(
        "email/email_consent.html",
        form=form,
        report=report,
        session=session,
        pharmacy=pharmacy,
        smtp_available=smtp_available,
    )
