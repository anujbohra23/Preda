import json
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request,
    jsonify, abort, current_app
)
from flask_login import login_required, current_user

from ..extensions import db
from ..models import (
    Session, ExtractedChunk, ChatMessage,
    RagRetrieval, AuditLog
)
from ..safety.triage import check_safety
from .pipeline import run_rag

chat_bp = Blueprint('chat', __name__, url_prefix='/chat')


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _own_session_or_404(session_id: int) -> Session:
    s = db.session.get(Session, session_id)
    if s is None or s.user_id != current_user.id:
        abort(404)
    return s


def _get_session_chunks(session_id: int):
    """
    Return parallel lists:
      chunk_texts  — the text to embed/retrieve (edited > original)
      chunk_db_ids — ExtractedChunk.id for each
      source_names — original filename for each
    """
    rows = (
        ExtractedChunk.query
        .filter_by(session_id=session_id, is_confirmed=1)
        .order_by(ExtractedChunk.chunk_index)
        .all()
    )
    chunk_texts  = []
    chunk_db_ids = []
    source_names = []

    for row in rows:
        text = row.edited_text if row.edited_text else row.chunk_text
        chunk_texts.append(text)
        chunk_db_ids.append(row.id)
        source_names.append(
            row.upload.original_name if row.upload else 'Document'
        )

    return chunk_texts, chunk_db_ids, source_names


def _log_audit(user_id: int, session_id: int, event: str, detail: dict):
    db.session.add(AuditLog(
        user_id      = user_id,
        session_id   = session_id,
        event_type   = event,
        event_detail = json.dumps(detail),
        created_at   = _utcnow(),
    ))


# ── Chat page (GET) ────────────────────────────────────────────────────────────

@chat_bp.route('/<int:session_id>')
@login_required
def chat_page(session_id):
    s = _own_session_or_404(session_id)

    messages = (
        s.chat_messages
        .order_by(ChatMessage.created_at)
        .all()
    )

    # Attach citations to each assistant message for display
    messages_with_citations = []
    for msg in messages:
        citations = []
        if msg.role == 'assistant':
            citations = (
                RagRetrieval.query
                .filter_by(chat_message_id=msg.id)
                .all()
            )
        messages_with_citations.append({
            'msg':       msg,
            'citations': citations,
        })

    has_docs = (
        ExtractedChunk.query
        .filter_by(session_id=session_id, is_confirmed=1)
        .count() > 0
    )

    # Update session status
    if s.status == 'results':
        s.status     = 'chat'
        s.updated_at = _utcnow()
        db.session.commit()

    return render_template(
        'chat/chat.html',
        session=s,
        messages_with_citations=messages_with_citations,
        has_docs=has_docs,
    )


# ── Send message (POST — JSON API) ────────────────────────────────────────────

@chat_bp.route('/<int:session_id>/message', methods=['POST'])
@login_required
def send_message(session_id):
    s = _own_session_or_404(session_id)

    data             = request.get_json(force=True)
    user_text        = (data.get('message') or '').strip()
    use_private_only = bool(data.get('use_private_only', True))

    if not user_text:
        return jsonify({'error': 'Message cannot be empty.'}), 400

    if len(user_text) > 2000:
        return jsonify({'error': 'Message too long (max 2000 chars).'}), 400

    # ── Save user message ──────────────────────────────────────────────────
    user_msg = ChatMessage(
        session_id       = session_id,
        role             = 'user',
        content          = user_text,
        use_private_only = int(use_private_only),
        safety_triggered = 0,
        created_at       = _utcnow(),
    )
    db.session.add(user_msg)
    db.session.flush()   # get user_msg.id

    # ── Quick safety check on user message ────────────────────────────────
    safety = check_safety(user_text)
    if safety['triggered']:
        user_msg.safety_triggered = 1
        s.safety_flagged          = 1
        s.updated_at              = _utcnow()

        # Log it
        _log_audit(current_user.id, session_id, 'safety_triggered', {
            'category':       safety['category'],
            'matched_phrase': safety['matched_phrase'],
        })

        # Save emergency assistant message
        assistant_msg = ChatMessage(
            session_id       = session_id,
            role             = 'assistant',
            content          = (
                f"🚨 {safety['emergency_message']} "
                "Please call emergency services immediately "
                "(911 / 999 / 112). "
                "Do not rely on this tool in an emergency."
            ),
            safety_triggered = 1,
            created_at       = _utcnow(),
        )
        db.session.add(assistant_msg)
        db.session.commit()

        return jsonify({
            'answer':            assistant_msg.content,
            'citations':         [],
            'safety_triggered':  True,
            'emergency_message': safety['emergency_message'],
        })

    # ── Load session chunks ────────────────────────────────────────────────
    chunk_texts, chunk_db_ids, source_names = _get_session_chunks(session_id)

    # ── Run RAG pipeline ───────────────────────────────────────────────────
    result = run_rag(
        session_id       = session_id,
        question         = user_text,
        chunks           = chunk_texts,
        chunk_db_ids     = chunk_db_ids,
        source_names     = source_names,
        use_private_only = use_private_only,
        top_n            = 5,
    )

    # ── Save assistant message ─────────────────────────────────────────────
    assistant_msg = ChatMessage(
        session_id       = session_id,
        role             = 'assistant',
        content          = result['answer'],
        use_private_only = int(use_private_only),
        safety_triggered = int(result['safety_triggered']),
        created_at       = _utcnow(),
    )
    db.session.add(assistant_msg)
    db.session.flush()

    # ── Save RAG retrievals (citations) ────────────────────────────────────
    for citation in result['citations']:
        if citation.get('chunk_id'):
            db.session.add(RagRetrieval(
                chat_message_id  = assistant_msg.id,
                chunk_id         = citation['chunk_id'],
                similarity_score = next(
                    (r['score'] for r in result['retrieved']
                     if r['chunk_index'] == result['citations'].index(citation)),
                    0.0
                ),
                citation_label   = citation['label'],
                source_doc_name  = citation['source_doc'],
            ))

    s.updated_at = _utcnow()
    db.session.commit()

    return jsonify({
        'answer':            result['answer'],
        'citations':         result['citations'],
        'safety_triggered':  result['safety_triggered'],
        'emergency_message': result.get('emergency_message'),
    })