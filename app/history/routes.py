from flask import Blueprint, render_template
from flask_login import login_required, current_user
from ..models import Session, DiseaseResult, ChatMessage, Report
from ..extensions import db

history_bp = Blueprint('history', __name__, url_prefix='/history')


@history_bp.route('/')
@login_required
def history():
    user_sessions = (
        Session.query
        .filter_by(user_id=current_user.id)
        .order_by(Session.created_at.desc())
        .all()
    )

    # Build summary stats per session
    session_stats = []
    for s in user_sessions:
        session_stats.append({
            'session': s,
            'disease_count': s.disease_results.count(),
            'message_count': s.chat_messages.count(),
            'report_count': s.reports.count(),
            'upload_count': s.uploads.count(),
        })

    return render_template('history/history.html', session_stats=session_stats)