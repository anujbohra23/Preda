import json
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import DiseaseResult, ExtractedChunk, Session
from ..twotower.retrieval import build_query_text, explain_match, retrieve_top_k

retrieve_bp = Blueprint("retrieve", __name__, url_prefix="/retrieve")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return s


# ── Results page ───────────────────────────────────────────────────────────────


@retrieve_bp.route("/<int:session_id>/results")
@login_required
def results(session_id):
    s = _own_session_or_404(session_id)

    # ── Gather intake fields ───────────────────────────────────────────────
    intake_fields = {f.field_name: f.field_value or "" for f in s.intake_fields.all()}

    if not intake_fields.get("chief_complaint"):
        flash("Please complete the intake form first.", "warning")
        return redirect(url_for("intake.intake_form", session_id=session_id))

    # ── Gather confirmed chunks ────────────────────────────────────────────
    confirmed_chunks = [
        (c.edited_text or c.chunk_text)
        for c in ExtractedChunk.query.filter_by(session_id=session_id, is_confirmed=1)
        .order_by(ExtractedChunk.chunk_index)
        .all()
    ]

    # ── Check if we already have results for this session ─────────────────
    existing_results = (
        DiseaseResult.query.filter_by(session_id=session_id)
        .order_by(DiseaseResult.rank)
        .all()
    )

    # Re-run retrieval only if no results yet OR if forced via query param
    if not existing_results:
        existing_results = _run_retrieval(s, intake_fields, confirmed_chunks)

    # ── Prepare display data ───────────────────────────────────────────────
    display_results = []
    for dr in existing_results:
        explanation = {}
        if dr.explanation_json:
            try:
                explanation = json.loads(dr.explanation_json)
            except (json.JSONDecodeError, TypeError):
                explanation = {}

        display_results.append(
            {
                "rank": dr.rank,
                "disease_name": dr.disease.disease_name,
                "icd_code": dr.disease.icd_code or "",
                "short_desc": dr.disease.short_desc or "",
                "similarity_score": dr.similarity_score,
                "matching_phrases": explanation.get("matching_phrases", []),
                "field_contributions": explanation.get("field_contributions", {}),
                "disease_result_id": dr.id,
            }
        )

    # Update session status
    if s.status not in ("chat", "report"):
        s.status = "results"
        s.updated_at = _utcnow()
        db.session.commit()

    return render_template(
        "retrieve/results.html",
        session=s,
        results=display_results,
        intake=intake_fields,
        has_upload=s.uploads.count() > 0,
    )


# ── Re-run retrieval ───────────────────────────────────────────────────────────


@retrieve_bp.route("/<int:session_id>/rerun", methods=["POST"])
@login_required
def rerun(session_id):
    s = _own_session_or_404(session_id)

    intake_fields = {f.field_name: f.field_value or "" for f in s.intake_fields.all()}
    confirmed_chunks = [
        (c.edited_text or c.chunk_text)
        for c in ExtractedChunk.query.filter_by(
            session_id=session_id, is_confirmed=1
        ).all()
    ]

    # Delete old results
    DiseaseResult.query.filter_by(session_id=session_id).delete()
    db.session.commit()

    _run_retrieval(s, intake_fields, confirmed_chunks)
    flash("Condition matching re-run with latest intake data.", "success")
    return redirect(url_for("retrieve.results", session_id=session_id))


# ── Internal helper ────────────────────────────────────────────────────────────


def _run_retrieval(
    session: Session, intake_fields: dict, confirmed_chunks: list[str]
) -> list[DiseaseResult]:
    """
    Run the full two-tower retrieval pipeline and persist results.
    Returns the list of DiseaseResult ORM objects.
    """
    try:
        query_text = build_query_text(intake_fields, confirmed_chunks)
        top_k = retrieve_top_k(query_text, k=10)
    except RuntimeError as e:
        flash(str(e), "error")
        return []

    saved = []
    for match in top_k:
        explanation = explain_match(match, intake_fields, confirmed_chunks)
        dr = DiseaseResult(
            session_id=session.id,
            disease_id=match["disease_id"],
            rank=match["rank"],
            similarity_score=match["similarity_score"],
            explanation_json=json.dumps(explanation),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        db.session.add(dr)
        saved.append(dr)

    db.session.commit()

    # Reload with relationships
    return (
        DiseaseResult.query.filter_by(session_id=session.id)
        .order_by(DiseaseResult.rank)
        .all()
    )
