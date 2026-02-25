"""
Safety triage layer.
- Emergency keyword detection
- Route guard decorator
- Citation sufficiency check
"""

import os
from functools import wraps

from flask import flash
from flask_login import current_user

# ── Emergency trigger categories ───────────────────────────────────────────────
EMERGENCY_TRIGGERS: dict[str, list[str]] = {
    "cardiac": [
        "chest pain",
        "chest tightness",
        "chest pressure",
        "left arm pain",
        "left arm numbness",
        "heart attack",
        "crushing chest",
        "jaw pain with chest",
    ],
    "stroke": [
        "facial drooping",
        "face drooping",
        "sudden numbness",
        "arm weakness",
        "slurred speech",
        "sudden severe headache",
        "vision loss",
        "stroke",
        "can't speak",
        "cannot speak",
    ],
    "respiratory": [
        "can't breathe",
        "cannot breathe",
        "can't catch my breath",
        "difficulty breathing",
        "stopped breathing",
        "choking",
        "not breathing",
    ],
    "mental_health_crisis": [
        "suicidal",
        "want to kill myself",
        "end my life",
        "kill myself",
        "self harm",
        "self-harm",
        "hurting myself",
        "want to die",
        "no reason to live",
    ],
    "severe_allergic": [
        "anaphylaxis",
        "throat closing",
        "throat swelling",
        "severe allergic",
        "epipen",
        "can't swallow",
        "cannot swallow",
    ],
    "unconscious": [
        "unconscious",
        "unresponsive",
        "passed out",
        "collapsed",
        "not waking up",
        "won't wake up",
    ],
}

EMERGENCY_MESSAGES: dict[str, str] = {
    "cardiac": "This sounds like a possible cardiac emergency.",
    "stroke": "These symptoms may indicate a stroke.",
    "respiratory": "Breathing difficulties require immediate emergency care.",
    "mental_health_crisis": "You are not alone. Please reach out for immediate help.",
    "severe_allergic": "Severe allergic reactions require immediate emergency care.",
    "unconscious": "An unconscious person needs emergency services immediately.",
}

MIN_RETRIEVAL_SCORE = float(os.environ.get("MIN_RETRIEVAL_SCORE", "0.05"))


def check_safety(text: str) -> dict:
    """
    Check text for emergency trigger phrases.
    Returns dict with triggered, category, matched_phrase, emergency_message.
    """
    text_lower = text.lower()
    for category, phrases in EMERGENCY_TRIGGERS.items():
        for phrase in phrases:
            if phrase in text_lower:
                return {
                    "triggered": True,
                    "category": category,
                    "matched_phrase": phrase,
                    "emergency_message": EMERGENCY_MESSAGES.get(category, ""),
                }
    return {
        "triggered": False,
        "category": None,
        "matched_phrase": None,
        "emergency_message": None,
    }


def is_retrieval_sufficient(retrieved_chunks: list[dict]) -> bool:
    if not retrieved_chunks:
        return False
    return any(c["score"] >= MIN_RETRIEVAL_SCORE for c in retrieved_chunks)


def check_intake_safety(intake_fields: dict) -> dict:
    """
    Run safety check across all intake fields combined.
    Used when saving intake to flag sessions before chat.
    """
    combined = " ".join(str(v) for v in intake_fields.values() if v)
    return check_safety(combined)


def safety_guard(session_getter):
    """
    Decorator factory for routes that take session_id.
    Flashes a persistent emergency warning if the session
    is safety-flagged, but still allows access.

    Usage:
        @sessions_bp.route('/<int:session_id>')
        @login_required
        @safety_guard(lambda sid: Session.query.get(sid))
        def detail(session_id): ...
    """

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            session_id = kwargs.get("session_id")
            if session_id and current_user.is_authenticated:
                from ..models import Session as SessionModel

                s = SessionModel.query.get(session_id)
                if s and s.safety_flagged and s.user_id == current_user.id:
                    flash(
                        "🚨 A safety alert was triggered in this session. "
                        "If you are in danger, call 911 / 999 / 112 immediately.",
                        "emergency",
                    )
            return f(*args, **kwargs)

        return wrapped

    return decorator
