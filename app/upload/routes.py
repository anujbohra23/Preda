from datetime import datetime, timezone
from flask import (
    Blueprint, render_template, redirect,
    url_for, flash, request, abort
)
from flask_login import login_required, current_user
from ..extensions import db
from ..models import Session, ExtractedChunk, Upload

upload_bp = Blueprint('upload', __name__, url_prefix='/upload')


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return s


# ── Review extracted chunks ────────────────────────────────────────────────────

@upload_bp.route('/<int:session_id>/review', methods=['GET', 'POST'])
@login_required
def review(session_id):
    s = _own_session_or_404(session_id)

    # Gather all unconfirmed chunks for this session
    chunks = (
        ExtractedChunk.query
        .filter_by(session_id=session_id)
        .order_by(ExtractedChunk.upload_id, ExtractedChunk.chunk_index)
        .all()
    )

    if not chunks:
        flash('No extracted text found for this session. '
              'Please upload a PDF first.', 'warning')
        return redirect(url_for('intake.intake_form', session_id=session_id))

    # Build a map of upload_id → original_name for display
    upload_names = {
        u.id: u.original_name
        for u in s.uploads.all()
    }

    if request.method == 'POST':
        # CSRF is validated automatically by Flask-WTF on all POST requests
        updated = 0
        for chunk in chunks:
            field_key = f'chunk_{chunk.id}'
            new_text = request.form.get(field_key, '').strip()
            if new_text:
                chunk.edited_text  = new_text
                chunk.is_confirmed = 1
                updated += 1

        # Mark all uploads as reviewed
        for upload in s.uploads.all():
            if upload.upload_status == 'extracted':
                upload.upload_status = 'reviewed'

        s.status     = 'results'
        s.updated_at = _utcnow()
        db.session.commit()

        flash(f'{updated} chunk(s) confirmed. Running condition matching…',
              'success')
        return redirect(url_for('retrieve.results', session_id=session_id))

    return render_template(
        'upload/review_extraction.html',
        session=s,
        chunks=chunks,
        upload_names=upload_names
    )