"""
app/appointments/summariser.py

Appointment summariser using Ollama (llama3.2:3b).
Takes raw transcript or manual notes and returns structured summary_json.
Language-aware: responds in Hindi when session lang == 'hi'.
"""
import json
import os

import requests

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "120"))


def summarise(text: str) -> dict:
    """
    Generate structured appointment summary from text.
    Language is determined from the active Flask session (en or hi).

    Returns { success, summary, error } where summary is a parsed dict.
    """
    if not text or len(text.strip()) < 10:
        return {
            "success": False,
            "summary": None,
            "error": "Text is too short to summarise.",
        }

    from ..lang.helpers import build_appointment_system_prompt, is_hindi

    system_prompt = build_appointment_system_prompt()

    if is_hindi():
        user_message = (
            f"नीचे अपॉइंटमेंट के नोट्स/ट्रांसक्रिप्ट हैं:\n\n{text}\n\n"
            "कृपया JSON सारांश निकालें और वापस करें।"
        )
    else:
        user_message = (
            f"Here are the appointment notes/transcript:\n\n{text}\n\n"
            "Please extract and return the structured JSON summary."
        )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{system_prompt}\n\nUser: {user_message}\n\nAssistant:",
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 800,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json().get("response", "").strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        summary = json.loads(raw)
        return {"success": True, "summary": summary, "error": None}

    except json.JSONDecodeError:
        return {
            "success": True,
            "summary": _fallback_summary(text, raw),
            "error": None,
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "summary": None,
            "error": "Ollama is not running. Start with: ollama serve",
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "summary": None,
            "error": f"Summarisation timed out after {OLLAMA_TIMEOUT}s.",
        }
    except Exception as e:
        return {"success": False, "summary": None, "error": str(e)}


def _fallback_summary(original_text: str, ollama_raw: str) -> dict:
    """Basic fallback when Ollama doesn't return valid JSON."""
    return {
        "what_doctor_said": ollama_raw[:500] if ollama_raw else original_text[:500],
        "medications": [],
        "tests_ordered": [],
        "lifestyle_changes": [],
        "warning_signs": [],
        "followup_date": None,
        "followup_instructions": None,
    }


def extract_actions(summary: dict) -> list[dict]:
    """Convert summary_json into a flat list of AppointmentAction dicts."""
    from ..lang.helpers import is_hindi

    if is_hindi():
        seek_medical = "यह होने पर तुरंत चिकित्सा सहायता लें।"
        followup_default = "अनुवर्ती अपॉइंटमेंट"
    else:
        seek_medical = "Seek medical attention if this occurs."
        followup_default = "Follow-up appointment"

    actions: list[dict] = []

    for med in summary.get("medications", []) or []:
        actions.append(
            {
                "action_type": "medication",
                "description": med.get("name", ""),
                "detail": (
                    f"{med.get('dosage', '')} — {med.get('frequency', '')}. "
                    f"{med.get('notes', '')}"
                ).strip(" —"),
                "due_date": None,
            }
        )

    for test in summary.get("tests_ordered", []) or []:
        actions.append(
            {
                "action_type": "test",
                "description": test.get("name", ""),
                "detail": (
                    f"{test.get('location', '')} — {test.get('urgency', '')}"
                ).strip(" —"),
                "due_date": None,
            }
        )

    for lc in summary.get("lifestyle_changes", []) or []:
        actions.append(
            {
                "action_type": "lifestyle",
                "description": lc.get("description", ""),
                "detail": None,
                "due_date": None,
            }
        )

    for ws in summary.get("warning_signs", []) or []:
        actions.append(
            {
                "action_type": "warning",
                "description": ws,
                "detail": seek_medical,
                "due_date": None,
            }
        )

    followup_date = summary.get("followup_date")
    followup_inst = summary.get("followup_instructions")
    if followup_inst or followup_date:
        actions.append(
            {
                "action_type": "followup",
                "description": followup_inst or followup_default,
                "detail": None,
                "due_date": followup_date,
            }
        )

    return actions
