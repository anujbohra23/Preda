"""
app/labs/routes.py

Lab value trend routes:
  GET  /labs/trends          — cross-session trend chart page
  GET  /labs/trends/data     — JSON API for chart data
  GET  /labs/<session_id>    — per-session lab values table
"""

from collections import defaultdict
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, render_template
from flask_login import current_user, login_required

from ..extensions import db
from ..models import LabValue, Session

labs_bp = Blueprint("labs", __name__, url_prefix="/labs")


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


# ── Trend page ─────────────────────────────────────────────────────────────────

@labs_bp.route("/trends")
@login_required
def trends():
    """Main lab trends page — shows Chart.js line charts per test."""
    # Get all tests this user has data for
    tests = (
        db.session.query(LabValue.test_name)
        .filter_by(user_id=current_user.id)
        .filter(LabValue.value.isnot(None))
        .distinct()
        .order_by(LabValue.test_name)
        .all()
    )
    test_names = [t[0] for t in tests]

    # Get session count with lab data
    sessions_with_labs = (
        db.session.query(LabValue.session_id)
        .filter_by(user_id=current_user.id)
        .distinct()
        .count()
    )

    return render_template(
        "labs/trends.html",
        test_names=test_names,
        sessions_with_labs=sessions_with_labs,
    )


# ── JSON API for chart data ────────────────────────────────────────────────────

@labs_bp.route("/trends/data")
@login_required
def trends_data():
    """
    Returns JSON for Chart.js:
    {
      "tests": {
        "HbA1c": {
          "unit": "%",
          "reference_range": "4.0-5.6",
          "points": [
            {"date": "2025-01-15", "value": 6.2, "session_id": 3,
             "session_title": "Jan checkup", "status": "high"},
            ...
          ]
        },
        ...
      }
    }
    """
    rows = (
        LabValue.query
        .filter_by(user_id=current_user.id)
        .filter(LabValue.value.isnot(None))
        .order_by(LabValue.report_date, LabValue.created_at)
        .all()
    )

    # Load session titles
    session_ids = {r.session_id for r in rows}
    sessions = {
        s.id: s for s in Session.query.filter(Session.id.in_(session_ids)).all()
    }

    # Group by test name
    tests: dict[str, dict] = {}
    for row in rows:
        if row.test_name not in tests:
            tests[row.test_name] = {
                "unit": row.unit or "",
                "reference_range": row.reference_range or "",
                "points": [],
            }

        s = sessions.get(row.session_id)
        # Use report_date if available, fall back to session created_at
        date = (
            row.report_date
            or (s.created_at[:10] if s else row.created_at[:10])
        )

        tests[row.test_name]["points"].append({
            "date":          date,
            "value":         row.value,
            "raw_value":     row.raw_value or str(row.value),
            "status":        row.status or "unknown",
            "session_id":    row.session_id,
            "session_title": s.title if s else f"Session {row.session_id}",
        })

        # Keep most common unit and reference range
        if row.unit and not tests[row.test_name]["unit"]:
            tests[row.test_name]["unit"] = row.unit
        if row.reference_range and not tests[row.test_name]["reference_range"]:
            tests[row.test_name]["reference_range"] = row.reference_range

    return jsonify({"tests": tests})


# ── Per-session lab table ──────────────────────────────────────────────────────

@labs_bp.route("/session/<int:session_id>")
@login_required
def session_labs(session_id):
    """Show all extracted lab values for a single session."""
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)

    labs = (
        LabValue.query
        .filter_by(session_id=session_id, user_id=current_user.id)
        .order_by(LabValue.test_name)
        .all()
    )

    # Group by test name to deduplicate (keep highest confidence)
    grouped: dict[str, LabValue] = {}
    for lab in labs:
        if lab.test_name not in grouped or lab.value is not None:
            grouped[lab.test_name] = lab

    return render_template(
        "labs/session_labs.html",
        session=s,
        labs=list(grouped.values()),
    )