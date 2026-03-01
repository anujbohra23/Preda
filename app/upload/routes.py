from collections import defaultdict
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import ExtractedChunk, Session

upload_bp = Blueprint("upload", __name__, url_prefix="/upload")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return s


@upload_bp.route("/<int:session_id>/review", methods=["GET", "POST"])
@login_required
def review(session_id):
    s = _own_session_or_404(session_id)

    chunks = (
        ExtractedChunk.query.filter_by(session_id=session_id)
        .order_by(ExtractedChunk.upload_id, ExtractedChunk.chunk_index)
        .all()
    )

    if not chunks:
        flash(
            "No extracted text found for this session. Please upload a PDF first.",
            "warning",
        )
        return redirect(url_for("intake.intake_form", session_id=session_id))

    upload_names = {u.id: u.original_name for u in s.uploads.all()}

    if request.method == "POST":
        updated = 0
        for chunk in chunks:
            field_key = f"chunk_{chunk.id}"
            new_text = request.form.get(field_key, "").strip()
            if new_text:
                chunk.edited_text = new_text
                chunk.is_confirmed = 1
                updated += 1

        for upload in s.uploads.all():
            if upload.upload_status == "extracted":
                upload.upload_status = "reviewed"

        s.status = "results"
        s.updated_at = _utcnow()
        db.session.commit()

        # ── Lab value extraction (non-critical, runs silently) ─────────────
        _extract_labs_for_session(s, chunks)

        flash(f"{updated} chunk(s) confirmed. Running condition matching…", "success")
        return redirect(url_for("retrieve.results", session_id=session_id))

    return render_template(
        "upload/review_extraction.html",
        session=s,
        chunks=chunks,
        upload_names=upload_names,
    )


def _extract_labs_for_session(session: Session, chunks: list) -> None:
    """
    Extract lab values from confirmed chunks and persist them.
    Silently catches all errors — never breaks the upload flow.
    """
    try:
        from ..labs.extractor import extract_from_chunks, save_lab_values

        by_upload: dict[int, list[str]] = defaultdict(list)
        for chunk in chunks:
            if chunk.is_confirmed:
                by_upload[chunk.upload_id].append(
                    chunk.edited_text or chunk.chunk_text
                )

        for upload_id, texts in by_upload.items():
            rows = extract_from_chunks(
                chunks=texts,
                session_id=session.id,
                upload_id=upload_id,
                user_id=session.user_id,
            )
            if rows:
                saved = save_lab_values(rows, upload_id)
                print(f"[labs] {saved} lab values saved from upload {upload_id}")

    except Exception as e:
        print(f"[labs] Extraction error (non-fatal): {e}")