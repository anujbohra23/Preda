"""
SMTP email sender for pharmacy report sharing.
Reads config from environment variables.
Supports Gmail, Outlook, and any standard SMTP server.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, timezone


# ── Config from environment ────────────────────────────────────────────────────
SMTP_HOST     = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT     = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER     = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMTP_FROM     = os.environ.get('SMTP_FROM', SMTP_USER)


def is_configured() -> bool:
    """Return True if SMTP credentials are set in environment."""
    return bool(SMTP_USER and SMTP_PASSWORD)


def send_pharmacy_report(
    recipient_email: str,
    recipient_name: str,
    sender_name: str,
    pdf_path: str,
    session_title: str,
    consent_note: str,
) -> dict:
    """
    Send the pharmacy PDF report to the given recipient.

    Returns:
        { success: bool, error: str | None }
    """
    if not is_configured():
        return {
            'success': False,
            'error':   (
                'Email is not configured. '
                'Add SMTP_USER and SMTP_PASSWORD to your .env file.'
            ),
        }

    if not os.path.exists(pdf_path):
        return {
            'success': False,
            'error':   'PDF file not found. Please regenerate the report.',
        }

    try:
        # ── Build message ──────────────────────────────────────────────────
        msg = MIMEMultipart()
        msg['From']    = f"HealthAssist <{SMTP_FROM}>"
        msg['To']      = f"{recipient_name} <{recipient_email}>"
        msg['Subject'] = (
            f"Informational Health Summary — {session_title}"
        )

        # ── Body ───────────────────────────────────────────────────────────
        sent_at = datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')
        body = f"""Dear {recipient_name},

{sender_name} has shared an informational health summary with you
via the HealthAssist tool.

IMPORTANT NOTICE:
This document is an informational summary only. It is NOT a prescription,
clinical diagnosis, or medical recommendation. All information must be
independently verified before any clinical action is taken.

Session: {session_title}
Sent: {sent_at}

Patient consent note:
"{consent_note}"

Please find the informational summary attached as a PDF.

---
This email was sent via HealthAssist MVP, an informational health tool.
If you received this in error, please disregard and delete it.
"""
        msg.attach(MIMEText(body, 'plain'))

        # ── Attach PDF ─────────────────────────────────────────────────────
        with open(pdf_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())

        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename="pharmacy_summary.pdf"'
        )
        msg.attach(part)

        # ── Send via SMTP ──────────────────────────────────────────────────
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(
                SMTP_FROM,
                recipient_email,
                msg.as_string()
            )

        return {'success': True, 'error': None}

    except smtplib.SMTPAuthenticationError:
        return {
            'success': False,
            'error':   (
                'SMTP authentication failed. '
                'Check your SMTP_USER and SMTP_PASSWORD in .env. '
                'For Gmail, use an App Password not your account password.'
            ),
        }
    except smtplib.SMTPException as e:
        return {'success': False, 'error': f'SMTP error: {e}'}
    except Exception as e:
        return {'success': False, 'error': f'Unexpected error: {e}'}