"""
RAG pipeline with Ollama (local LLM) as the answer synthesizer.

Two modes:
  - doc_grounded  (score >= 0.25): answer comes from document chunks, cited
  - general       (score <  0.25): answer from Ollama general medical knowledge,
                                   document shown as background context only,
                                   no citations returned

Flow:
  1. Safety check
  2. Build/retrieve FAISS index
  3. Retrieve top-N chunks
  4. Score check → pick mode
  5. Call Ollama with mode-appropriate prompt
  6. Return answer + citations (empty in general mode)
"""

import os

import requests

from ..safety.triage import check_safety
from .vector_store import build_session_index, retrieve_chunks, session_index_exists

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT  = int(os.environ.get("OLLAMA_TIMEOUT", "60"))

# Chunks above this score are treated as genuinely relevant to the question
GOOD_RETRIEVAL_THRESHOLD = float(os.environ.get("GOOD_RETRIEVAL_THRESHOLD", "0.25"))


# ── System prompts — document-grounded mode ────────────────────────────────────

SYSTEM_DOC_EN = (
    "You are a health document assistant helping a patient understand their "
    "medical documents.\n\n"
    "RULES:\n"
    "1. Answer using the provided document chunks as your primary source.\n"
    "2. Cite every factual claim from the document using [1], [2], [3].\n"
    "3. If the document does not fully answer the question, use your general "
    "medical knowledge to fill the gap — but clearly say it is general "
    "information, not from the document.\n"
    "4. NEVER invent lab values, names, or dates from the document.\n"
    "5. NEVER provide a diagnosis or treatment recommendation.\n"
    "6. Write in clear, simple language a non-medical person can understand.\n"
    "7. Keep your answer to 4-6 sentences maximum.\n"
    '8. Always end with: "⚕ This is informational only. '
    'Please consult your healthcare provider."\n'
)

SYSTEM_DOC_HI = (
    "आप एक स्वास्थ्य दस्तावेज़ सहायक हैं। हमेशा हिंदी में जवाब दें।\n\n"
    "नियम:\n"
    "1. दिए गए दस्तावेज़ खंडों को प्राथमिक स्रोत के रूप में उपयोग करें।\n"
    "2. दस्तावेज़ से हर तथ्यात्मक दावे को [1], [2], [3] से उद्धृत करें।\n"
    "3. यदि दस्तावेज़ में पूरा उत्तर नहीं है, तो सामान्य चिकित्सा ज्ञान से "
    "उत्तर दें — लेकिन स्पष्ट रूप से बताएं।\n"
    "4. लैब मूल्य, नाम या तारीखें कभी न बनाएं।\n"
    "5. निदान या उपचार की सिफारिश न करें।\n"
    "6. सरल हिंदी में, अधिकतम 4-6 वाक्य।\n"
    '7. हमेशा इस पंक्ति के साथ समाप्त करें: "⚕ यह केवल सूचनात्मक है। '
    'कृपया अपने स्वास्थ्य सेवा प्रदाता से परामर्श लें।"\n'
)

# ── System prompts — general knowledge mode ────────────────────────────────────

SYSTEM_GENERAL_EN = (
    "You are a helpful health assistant. A patient has a medical question. "
    "Their uploaded documents are provided as background context.\n\n"
    "RULES:\n"
    "1. Answer the patient's question using your general medical knowledge.\n"
    "2. If the patient's documents contain relevant information, mention it.\n"
    "3. NEVER provide a diagnosis or treatment recommendation.\n"
    "4. Write in clear, simple language a non-medical person can understand.\n"
    "5. Keep your answer to 4-6 sentences maximum.\n"
    '6. Always end with: "⚕ This is informational only. '
    'Please consult your healthcare provider."\n'
)

SYSTEM_GENERAL_HI = (
    "आप एक सहायक स्वास्थ्य सहायक हैं। एक मरीज का चिकित्सा प्रश्न है। "
    "हमेशा हिंदी में जवाब दें।\n\n"
    "नियम:\n"
    "1. अपने सामान्य चिकित्सा ज्ञान से प्रश्न का उत्तर दें।\n"
    "2. यदि मरीज के दस्तावेज़ में प्रासंगिक जानकारी हो तो उसका उल्लेख करें।\n"
    "3. निदान या उपचार की सिफारिश न करें।\n"
    "4. सरल हिंदी में, अधिकतम 4-6 वाक्य।\n"
    '5. हमेशा इस पंक्ति के साथ समाप्त करें: "⚕ यह केवल सूचनात्मक है। '
    'कृपया अपने स्वास्थ्य सेवा प्रदाता से परामर्श लें।"\n'
)

NO_DOCS_EN = (
    "No documents are available for this session. "
    "Please upload a PDF and confirm the extracted text first."
)

NO_DOCS_HI = (
    "इस सत्र के लिए कोई दस्तावेज़ उपलब्ध नहीं है। "
    "कृपया पहले एक PDF अपलोड करें और निकाले गए पाठ की पुष्टि करें।"
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _is_hindi() -> bool:
    try:
        from ..lang.helpers import is_hindi
        return is_hindi()
    except RuntimeError:
        return False


def _best_score(retrieved: list[dict]) -> float:
    return max((c.get("score", 0.0) for c in retrieved), default=0.0)


def _is_doc_grounded(retrieved: list[dict]) -> bool:
    """True if at least one chunk is genuinely relevant to the question."""
    return _best_score(retrieved) >= GOOD_RETRIEVAL_THRESHOLD


# ── Ollama caller ──────────────────────────────────────────────────────────────

def _call_ollama(question: str, retrieved: list[dict], doc_grounded: bool) -> str:
    hindi = _is_hindi()

    system_prompt = (
        (SYSTEM_DOC_HI if hindi else SYSTEM_DOC_EN)
        if doc_grounded
        else (SYSTEM_GENERAL_HI if hindi else SYSTEM_GENERAL_EN)
    )

    # Numbered context from chunks
    context = "\n\n".join(
        f"[{i+1}] {r['text'][:600]}" for i, r in enumerate(retrieved)
    )

    if hindi:
        if doc_grounded:
            user_message = (
                f"दस्तावेज़ खंड:\n\n{context}\n\n"
                f"मरीज का प्रश्न: {question}\n\n"
                "खंडों के आधार पर उत्तर दें और [1], [2], [3] से उद्धृत करें।"
            )
        else:
            user_message = (
                f"पृष्ठभूमि संदर्भ (मरीज के दस्तावेज़):\n\n{context}\n\n"
                f"मरीज का प्रश्न: {question}\n\n"
                "अपने सामान्य चिकित्सा ज्ञान से उत्तर दें।"
            )
    else:
        if doc_grounded:
            user_message = (
                f"Document chunks:\n\n{context}\n\n"
                f"Patient's question: {question}\n\n"
                "Answer using the chunks above. Cite sources with [1], [2], [3]."
            )
        else:
            user_message = (
                f"Background context (patient's documents):\n\n{context}\n\n"
                f"Patient's question: {question}\n\n"
                "Answer using your general medical knowledge. "
                "Reference the patient's documents only if directly relevant."
            )

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": f"{system_prompt}\n\nUser: {user_message}\n\nAssistant:",
        "stream": False,
        "options": {
            "temperature": 0.2 if doc_grounded else 0.3,
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
        answer = response.json().get("response", "").strip()
        return answer if answer else _fallback_answer(retrieved)

    except requests.exceptions.ConnectionError:
        print("[RAG] Ollama not running. Start with: ollama serve")
        return _fallback_answer(retrieved)
    except requests.exceptions.Timeout:
        print(f"[RAG] Ollama timed out after {OLLAMA_TIMEOUT}s.")
        return _fallback_answer(retrieved)
    except Exception as e:
        print(f"[RAG] Ollama error: {e}")
        return _fallback_answer(retrieved)


# ── Offline fallback ───────────────────────────────────────────────────────────

def _fallback_answer(retrieved: list[dict]) -> str:
    """Keyword extraction fallback when Ollama is offline."""
    LAB_KEYWORDS = {
        "NORMAL", "HIGH", "LOW", "RESULT", "SODIUM", "POTASSIUM", "GLUCOSE",
        "HEMOGLOBIN", "CREATININE", "CHOLESTEROL", "PHYSICIAN", "DATE",
        "COLLECTED", "REPORTED", "PATIENT", "SPECIMEN", "WBC", "RBC",
        "PLATELET", "CALCIUM", "PROTEIN",
    }
    hindi = _is_hindi()

    lines = []
    for i, result in enumerate(retrieved[:3]):
        meaningful = [
            ln.strip() for ln in result["text"].split("\n")
            if len(ln.strip()) > 10
            and any(kw in ln.upper() for kw in LAB_KEYWORDS)
        ]
        if meaningful:
            lines.append(f"[{i+1}] " + " | ".join(meaningful[:4]))

    if hindi:
        disclaimer = "\n\n⚕ यह केवल सूचनात्मक है। कृपया अपने स्वास्थ्य सेवा प्रदाता से परामर्श लें।"
        prefix, fallback_prefix = "आपके दस्तावेज़ों से:\n\n", "आपके दस्तावेज़ों से [1]: "
    else:
        disclaimer = "\n\n⚕ This is informational only. Please consult your healthcare provider."
        prefix, fallback_prefix = "From your documents:\n\n", "From your documents [1]: "

    if lines:
        return prefix + "\n".join(lines) + disclaimer
    top = retrieved[0]["text"][:300] if retrieved else ""
    return f"{fallback_prefix}{top}...{disclaimer}"


# ── Index helpers ──────────────────────────────────────────────────────────────

def ensure_index(session_id: int, chunks: list[str]) -> bool:
    if session_index_exists(session_id):
        return True
    return build_session_index(session_id, chunks)


# ── Main entry point ───────────────────────────────────────────────────────────

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

    Returns { answer, citations, safety_triggered, emergency_message,
              retrieved, doc_grounded }
    """
    hindi = _is_hindi()

    # ── 1. Safety check ────────────────────────────────────────────────────
    safety = check_safety(question)
    if safety["triggered"]:
        answer = (
            f"⚠️ {safety['emergency_message']} "
            + ("कृपया तुरंत आपातकालीन सेवाओं को कॉल करें (112)। "
               "आपात स्थिति में इस उपकरण पर निर्भर न रहें।"
               if hindi else
               "Please call emergency services immediately (911 / 999 / 112). "
               "Do not rely on this tool in an emergency.")
        )
        return {
            "answer": answer,
            "citations": [],
            "safety_triggered": True,
            "emergency_message": safety["emergency_message"],
            "retrieved": [],
            "doc_grounded": False,
        }

    # ── 2. No documents ────────────────────────────────────────────────────
    if not chunks:
        return {
            "answer": NO_DOCS_HI if hindi else NO_DOCS_EN,
            "citations": [],
            "safety_triggered": False,
            "emergency_message": None,
            "retrieved": [],
            "doc_grounded": False,
        }

    # ── 3. Build FAISS index ───────────────────────────────────────────────
    ensure_index(session_id, chunks)

    # ── 4. Retrieve top-N chunks ───────────────────────────────────────────
    retrieved = retrieve_chunks(session_id, question, top_n=top_n)

    # ── 5. Choose mode ─────────────────────────────────────────────────────
    doc_grounded = _is_doc_grounded(retrieved)

    # ── 6. Call Ollama ─────────────────────────────────────────────────────
    answer = _call_ollama(question, retrieved, doc_grounded)

    # ── 7. Citations — only when doc-grounded ──────────────────────────────
    # In general-knowledge mode, citations are omitted to avoid implying
    # the document contained information that it did not.
    citations = []
    if doc_grounded:
        for i, result in enumerate(retrieved):
            chunk_idx = result["chunk_index"]
            citations.append({
                "label": f"[{i+1}]",
                "chunk_id": (
                    chunk_db_ids[chunk_idx]
                    if chunk_idx < len(chunk_db_ids) else None
                ),
                "source_doc": (
                    source_names[chunk_idx]
                    if chunk_idx < len(source_names) else "Document"
                ),
                "excerpt": result["text"][:300],
            })

    return {
        "answer": answer,
        "citations": citations,
        "safety_triggered": False,
        "emergency_message": None,
        "retrieved": retrieved,
        "doc_grounded": doc_grounded,
    }