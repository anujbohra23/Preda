"""
app/lang/helpers.py

Language helpers for all Ollama prompts.
When session lang == 'hi', Ollama ALWAYS responds in Hindi
regardless of what language the user typed in.

Usage:
    from ..lang.helpers import is_hindi, build_rag_prompt, build_appointment_system_prompt
"""
from flask import session


def get_active_language() -> str:
    """Return 'en' or 'hi' from session. Default: 'en'."""
    lang = session.get("lang", "en")
    return lang if lang in ("en", "hi") else "en"


def is_hindi() -> bool:
    return get_active_language() == "hi"


# ── RAG chat ───────────────────────────────────────────────────────────────────

def build_rag_prompt(context: str, question: str) -> str:
    """
    Build the complete RAG prompt string in the active language.
    Pass this as the `prompt` field to Ollama directly.
    """
    if is_hindi():
        return (
            "आप एक सहायक स्वास्थ्य AI हैं जो मरीजों को उनके चिकित्सा दस्तावेज़ "
            "समझने में मदद करता है।\n\n"
            "महत्वपूर्ण निर्देश: आपको हमेशा हिंदी में जवाब देना है। "
            "देवनागरी लिपि का उपयोग करें। "
            "चिकित्सा शब्दों को सरल भाषा में समझाएं।\n\n"
            "नियम:\n"
            "1. केवल नीचे दिए गए संदर्भ दस्तावेज़ों की जानकारी उपयोग करें।\n"
            "2. यदि संदर्भ में उत्तर नहीं है, स्पष्ट रूप से कहें।\n"
            "3. सरल, स्पष्ट हिंदी में उत्तर दें।\n"
            "4. उत्तर के अंत में स्रोत दस्तावेज़ का उल्लेख करें।\n"
            "5. यह चिकित्सा सलाह नहीं है — डॉक्टर से परामर्श लें।\n\n"
            f"संदर्भ दस्तावेज़:\n{context}\n\n"
            f"मरीज का प्रश्न: {question}\n\n"
            "उत्तर (हिंदी में):"
        )
    return (
        "You are a helpful health AI that helps patients understand "
        "their medical documents.\n\n"
        "Rules:\n"
        "1. Only use information from the provided context documents.\n"
        "2. If the answer is not in the context, say so clearly.\n"
        "3. Always respond in clear, simple English — no complex medical jargon.\n"
        "4. Cite the source document at the end of your response.\n"
        "5. Remind the user this is not medical advice — consult a doctor.\n\n"
        f"Context documents:\n{context}\n\n"
        f"Patient question: {question}\n\n"
        "Answer:"
    )


# ── Appointment summariser ─────────────────────────────────────────────────────

_APPT_PROMPT_HI = (
    "आप एक चिकित्सा अपॉइंटमेंट सारांशकर्ता हैं।\n"
    "अपॉइंटमेंट नोट्स पढ़ें और संरचित जानकारी निकालें।\n\n"
    "महत्वपूर्ण: केवल JSON में जवाब दें — कोई markdown नहीं, "
    "कोई अतिरिक्त पाठ नहीं।\n"
    "सरल हिंदी का उपयोग करें। जो नोट्स में नहीं है उसे न बनाएं।\n\n"
    "इस JSON संरचना के साथ उत्तर दें:\n"
    "{\n"
    '  "what_doctor_said": "डॉक्टर ने क्या कहा — सरल हिंदी में 2-3 वाक्य",\n'
    '  "medications": [\n'
    '    {"name": "दवा का नाम", "dosage": "खुराक", '
    '"frequency": "कितनी बार", "notes": "नोट"}\n'
    "  ],\n"
    '  "tests_ordered": [\n'
    '    {"name": "परीक्षण का नाम", "location": "स्थान", "urgency": "कब तक"}\n'
    "  ],\n"
    '  "lifestyle_changes": [{"description": "जीवनशैली में बदलाव"}],\n'
    '  "warning_signs": ["चेतावनी संकेत 1", "चेतावनी संकेत 2"],\n'
    '  "followup_date": "YYYY-MM-DD या null",\n'
    '  "followup_instructions": "अनुवर्ती निर्देश"\n'
    "}"
)

_APPT_PROMPT_EN = (
    "You are a medical appointment summariser. Your job is to read appointment "
    "notes or transcripts and extract structured information to help the patient "
    "remember what happened and what they need to do.\n\n"
    "RULES:\n"
    "1. Always respond with valid JSON only — no markdown, no extra text.\n"
    "2. Use plain, simple English a non-medical person can understand.\n"
    "3. If information is not mentioned, use null for that field.\n"
    "4. Never invent information not present in the notes.\n"
    "5. Be concise but complete.\n\n"
    "Respond with exactly this JSON structure:\n"
    "{\n"
    '  "what_doctor_said": "2-3 sentence plain English summary of the'
    " doctor's findings\",\n"
    '  "medications": [\n'
    '    {"name": "...", "dosage": "...", "frequency": "...", "notes": "..."}\n'
    "  ],\n"
    '  "tests_ordered": [\n'
    '    {"name": "...", "location": "...", "urgency": "..."}\n'
    "  ],\n"
    '  "lifestyle_changes": [{"description": "..."}],\n'
    '  "warning_signs": ["...", "..."],\n'
    '  "followup_date": "YYYY-MM-DD or null",\n'
    '  "followup_instructions": "..."\n'
    "}"
)


def build_appointment_system_prompt() -> str:
    """Return appointment summariser system prompt in the active language."""
    return _APPT_PROMPT_HI if is_hindi() else _APPT_PROMPT_EN
