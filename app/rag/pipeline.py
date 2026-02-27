"""
RAG pipeline with Ollama (local LLM) as the answer synthesizer.

Flow:
  1. Safety check
  2. Build/retrieve FAISS index
  3. Retrieve top-N chunks
  4. Citations-required policy check
  5. Send chunks + question to Ollama (in active language)
  6. Return answer with citations
"""

import os

import requests

from ..safety.triage import check_safety, is_retrieval_sufficient
from .vector_store import build_session_index, retrieve_chunks, session_index_exists

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))


# ── Language-aware system prompts ──────────────────────────────────────────────

SYSTEM_PROMPT_EN = (
    "You are a health document assistant helping a patient understand their "
    "medical documents.\n\n"
    "RULES you must always follow:\n"
    "1. Answer ONLY using the provided document chunks below.\n"
    "2. Cite every factual claim using [1], [2], [3] matching the chunk numbers.\n"
    "3. If the answer is not in the chunks, say exactly:\n"
    '   "I don\'t know based on the available documents."\n'
    "4. NEVER invent medical facts, lab values, names, or dates.\n"
    "5. NEVER provide a diagnosis or treatment recommendation.\n"
    "6. Write in clear, simple language a non-medical person can understand.\n"
    "7. Keep your answer to 4-6 sentences maximum.\n"
    "8. Always end with this exact line:\n"
    '   "⚕ This is informational only. Please consult your healthcare provider."\n'
)

SYSTEM_PROMPT_HI = (
    "आप एक स्वास्थ्य दस्तावेज़ सहायक हैं जो मरीज को उनके चिकित्सा दस्तावेज़ "
    "समझने में मदद करते हैं।\n\n"
    "महत्वपूर्ण: आपको हमेशा हिंदी में जवाब देना है। देवनागरी लिपि का उपयोग करें।\n\n"
    "नियम जिनका आपको हमेशा पालन करना है:\n"
    "1. केवल नीचे दिए गए दस्तावेज़ खंडों का उपयोग करके उत्तर दें।\n"
    "2. हर तथ्यात्मक दावे को [1], [2], [3] से उद्धृत करें।\n"
    "3. यदि उत्तर खंडों में नहीं है, तो बिल्कुल यह कहें:\n"
    '   "उपलब्ध दस्तावेज़ों के आधार पर मुझे नहीं पता।"\n'
    "4. कभी भी चिकित्सा तथ्य, लैब मूल्य, नाम या तारीखें न बनाएं।\n"
    "5. कभी भी निदान या उपचार की सिफारिश न करें।\n"
    "6. सरल, स्पष्ट हिंदी में लिखें जो गैर-चिकित्सा व्यक्ति समझ सके।\n"
    "7. अपना उत्तर अधिकतम 4-6 वाक्यों तक सीमित रखें।\n"
    "8. हमेशा इस पंक्ति के साथ समाप्त करें:\n"
    '   "⚕ यह केवल सूचनात्मक है। कृपया अपने स्वास्थ्य सेवा प्रदाता से परामर्श लें।"\n'
)

DONT_KNOW_EN = (
    "I don't know based on the available documents. "
    "Could you clarify your question or upload additional documents "
    "that might contain relevant information?"
)

DONT_KNOW_HI = (
    "उपलब्ध दस्तावेज़ों के आधार पर मुझे नहीं पता। "
    "क्या आप अपना प्रश्न स्पष्ट कर सकते हैं या ऐसे अतिरिक्त दस्तावेज़ "
    "अपलोड कर सकते हैं जिनमें प्रासंगिक जानकारी हो?"
)

NO_DOCS_EN = (
    "No documents are available for this session. "
    "Please upload a PDF and confirm the extracted text first."
)

NO_DOCS_HI = (
    "इस सत्र के लिए कोई दस्तावेज़ उपलब्ध नहीं है। "
    "कृपया पहले एक PDF अपलोड करें और निकाले गए पाठ की पुष्टि करें।"
)


def _get_prompts():
    """Return (system_prompt, dont_know, no_docs, user_message_prefix) for active lang."""
    try:
        from ..lang.helpers import is_hindi
        hindi = is_hindi()
    except RuntimeError:
        # Outside app context (e.g. tests) — default to English
        hindi = False

    if hindi:
        return SYSTEM_PROMPT_HI, DONT_KNOW_HI, NO_DOCS_HI, "hi"
    return SYSTEM_PROMPT_EN, DONT_KNOW_EN, NO_DOCS_EN, "en"


# ── Ollama caller ──────────────────────────────────────────────────────────────


def _call_ollama(question: str, retrieved: list[dict]) -> str:
    """
    Send the question + retrieved chunks to Ollama and get a synthesized answer.
    Prompt language matches the active Flask session language.
    """
    system_prompt, dont_know, no_docs, lang = _get_prompts()

    # Build numbered context
    context_parts = []
    for i, result in enumerate(retrieved):
        context_parts.append(f"[{i + 1}] {result['text'][:600]}")
    context = "\n\n".join(context_parts)

    if lang == "hi":
        user_message = (
            "नीचे मरीज के दस्तावेज़ों के प्रासंगिक खंड हैं:\n\n"
            f"{context}\n\n"
            f"मरीज का प्रश्न: {question}\n\n"
            "केवल ऊपर दिए गए खंडों का उपयोग करके उत्तर दें। "
            "अपने स्रोतों को उद्धृत करने के लिए [1], [2], [3] का उपयोग करें।"
        )
    else:
        user_message = (
            "Here are the relevant chunks from the patient's documents:\n\n"
            f"{context}\n\n"
            f"Patient's question: {question}\n\n"
            "Answer using ONLY the chunks above. "
            "Use [1], [2], [3] to cite your sources."
        )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{system_prompt}\n\nUser: {user_message}\n\nAssistant:",
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 400,
        },
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        answer = data.get("response", "").strip()

        if not answer:
            return _fallback_answer(retrieved)

        return answer

    except requests.exceptions.ConnectionError:
        print("[RAG] Ollama not running. Start with: ollama serve")
        return _fallback_answer(retrieved)

    except requests.exceptions.Timeout:
        print(f"[RAG] Ollama timed out after {OLLAMA_TIMEOUT}s.")
        return _fallback_answer(retrieved)

    except Exception as e:
        print(f"[RAG] Ollama error: {e}")
        return _fallback_answer(retrieved)


# ── Fallback when Ollama is offline ───────────────────────────────────────────


def _fallback_answer(retrieved: list[dict]) -> str:
    """Structured extraction fallback — no LLM needed."""
    LAB_KEYWORDS = {
        "NORMAL", "HIGH", "LOW", "RESULT", "SODIUM", "POTASSIUM", "GLUCOSE",
        "HEMOGLOBIN", "CREATININE", "CHOLESTEROL", "PHYSICIAN", "DATE",
        "COLLECTED", "REPORTED", "PATIENT", "SPECIMEN", "WBC", "RBC",
        "PLATELET", "CALCIUM", "PROTEIN",
    }

    try:
        from ..lang.helpers import is_hindi
        hindi = is_hindi()
    except RuntimeError:
        hindi = False

    lines = []
    for i, result in enumerate(retrieved[:3]):
        meaningful = []
        for line in result["text"].split("\n"):
            line = line.strip()
            if len(line) > 10 and any(kw in line.upper() for kw in LAB_KEYWORDS):
                meaningful.append(line)
        if meaningful:
            lines.append(f"[{i + 1}] " + " | ".join(meaningful[:4]))

    if hindi:
        disclaimer = "\n\n⚕ यह केवल सूचनात्मक है। कृपया अपने स्वास्थ्य सेवा प्रदाता से परामर्श लें।"
        prefix = "आपके दस्तावेज़ों से:\n\n"
        fallback_prefix = "आपके दस्तावेज़ों से [1]: "
    else:
        disclaimer = "\n\n⚕ This is informational only. Please consult your healthcare provider."
        prefix = "From your documents:\n\n"
        fallback_prefix = "From your documents [1]: "

    if lines:
        return prefix + "\n".join(lines) + disclaimer

    top = retrieved[0]["text"][:300] if retrieved else ""
    return f"{fallback_prefix}{top}...{disclaimer}"


# ── Index helpers ──────────────────────────────────────────────────────────────


def ensure_index(session_id: int, chunks: list[str]) -> bool:
    if session_index_exists(session_id):
        return True
    return build_session_index(session_id, chunks)


# ── Main RAG entry point ───────────────────────────────────────────────────────


def run_rag(
    session_id: int,
    question: str,
    chunks: list[str],
    chunk_db_ids: list[int],
    source_names: list[str],
    use_private_only: bool = True,
    top_n: int = 5,
) -> dict:
    """
    Full RAG pipeline for one user question.

    Returns:
    {
        answer, citations, safety_triggered,
        emergency_message, retrieved
    }
    """
    _, dont_know, no_docs, lang = _get_prompts()

    # ── 1. Safety check ────────────────────────────────────────────────────
    safety = check_safety(question)
    if safety["triggered"]:
        if lang == "hi":
            answer = (
                f"⚠️ {safety['emergency_message']} "
                "कृपया तुरंत आपातकालीन सेवाओं को कॉल करें (112)। "
                "आपात स्थिति में इस उपकरण पर निर्भर न रहें।"
            )
        else:
            answer = (
                f"⚠️ {safety['emergency_message']} "
                "Please call emergency services immediately "
                "(911 / 999 / 112). "
                "Do not rely on this tool in an emergency."
            )
        return {
            "answer": answer,
            "citations": [],
            "safety_triggered": True,
            "emergency_message": safety["emergency_message"],
            "retrieved": [],
        }

    # ── 2. Ensure FAISS index ──────────────────────────────────────────────
    if not chunks:
        return {
            "answer": no_docs,
            "citations": [],
            "safety_triggered": False,
            "emergency_message": None,
            "retrieved": [],
        }

    ensure_index(session_id, chunks)

    # ── 3. Retrieve top-N chunks ───────────────────────────────────────────
    retrieved = retrieve_chunks(session_id, question, top_n=top_n)

    # ── 4. Citations-required policy ───────────────────────────────────────
    if not is_retrieval_sufficient(retrieved):
        return {
            "answer": dont_know,
            "citations": [],
            "safety_triggered": False,
            "emergency_message": None,
            "retrieved": retrieved,
        }

    # ── 5. Synthesize with Ollama ──────────────────────────────────────────
    answer = _call_ollama(question, retrieved)

    # ── 6. Build citations ─────────────────────────────────────────────────
    citations = []
    for i, result in enumerate(retrieved):
        chunk_idx = result["chunk_index"]
        chunk_db_id = chunk_db_ids[chunk_idx] if chunk_idx < len(chunk_db_ids) else None
        source_name = (
            source_names[chunk_idx] if chunk_idx < len(source_names) else "Document"
        )
        citations.append(
            {
                "label": f"[{i + 1}]",
                "chunk_id": chunk_db_id,
                "source_doc": source_name,
                "excerpt": result["text"][:300],
            }
        )

    return {
        "answer": answer,
        "citations": citations,
        "safety_triggered": False,
        "emergency_message": None,
        "retrieved": retrieved,
    }
