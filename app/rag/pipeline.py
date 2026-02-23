"""
RAG pipeline with Ollama (local LLM) as the answer synthesizer.

Flow:
  1. Safety check
  2. Build/retrieve FAISS index
  3. Retrieve top-N chunks
  4. Citations-required policy check
  5. Send chunks + question to Ollama
  6. Return answer with citations
"""
import os
import requests

from .vector_store import (
    build_session_index,
    retrieve_chunks,
    session_index_exists,
)
from ..safety.triage import check_safety, is_retrieval_sufficient


# ── Ollama config (set in .env to override) ────────────────────────────────────
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
OLLAMA_MODEL    = os.environ.get('OLLAMA_MODEL', 'llama3.2:3b')
OLLAMA_TIMEOUT  = int(os.environ.get('OLLAMA_TIMEOUT', '60'))


# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a health document assistant helping a patient 
understand their medical documents.

RULES you must always follow:
1. Answer ONLY using the provided document chunks below.
2. Cite every factual claim using [1], [2], [3] matching the chunk numbers.
3. If the answer is not in the chunks, say exactly:
   "I don't know based on the available documents."
4. NEVER invent medical facts, lab values, names, or dates.
5. NEVER provide a diagnosis or treatment recommendation.
6. Write in clear, simple language a non-medical person can understand.
7. Keep your answer to 4-6 sentences maximum.
8. Always end with this exact line:
   "⚕ This is informational only. Please consult your healthcare provider."
"""


DONT_KNOW = (
    "I don't know based on the available documents. "
    "Could you clarify your question or upload additional documents "
    "that might contain relevant information?"
)


# ── Ollama caller ──────────────────────────────────────────────────────────────

def _call_ollama(question: str, retrieved: list[dict]) -> str:
    """
    Send the question + retrieved chunks to Ollama and get a synthesized answer.
    Falls back to structured extraction if Ollama is not running.
    """
    # Build numbered context
    context_parts = []
    for i, result in enumerate(retrieved):
        context_parts.append(f"[{i+1}] {result['text'][:600]}")
    context = "\n\n".join(context_parts)

    # Full prompt
    user_message = (
        f"Here are the relevant chunks from the patient's documents:\n\n"
        f"{context}\n\n"
        f"Patient's question: {question}\n\n"
        f"Answer using ONLY the chunks above. "
        f"Use [1], [2], [3] to cite your sources."
    )

    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": f"{SYSTEM_PROMPT}\n\nUser: {user_message}\n\nAssistant:",
        "stream": False,
        "options": {
            "temperature": 0.1,    # low temp = more factual, less creative
            "num_predict": 400,    # max tokens in response
        }
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        answer = data.get('response', '').strip()

        if not answer:
            return _fallback_answer(retrieved)

        return answer

    except requests.exceptions.ConnectionError:
        print(
            "[RAG] Ollama not running. "
            "Start with: ollama serve"
        )
        return _fallback_answer(retrieved)

    except requests.exceptions.Timeout:
        print(f"[RAG] Ollama timed out after {OLLAMA_TIMEOUT}s.")
        return _fallback_answer(retrieved)

    except Exception as e:
        print(f"[RAG] Ollama error: {e}")
        return _fallback_answer(retrieved)


# ── Fallback when Ollama is offline ───────────────────────────────────────────

def _fallback_answer(retrieved: list[dict]) -> str:
    """
    Structured extraction fallback — no LLM needed.
    Pulls readable lines from lab report style text.
    """
    LAB_KEYWORDS = {
        'NORMAL', 'HIGH', 'LOW', 'RESULT', 'SODIUM', 'POTASSIUM',
        'GLUCOSE', 'HEMOGLOBIN', 'CREATININE', 'CHOLESTEROL',
        'PHYSICIAN', 'DATE', 'COLLECTED', 'REPORTED', 'PATIENT',
        'SPECIMEN', 'WBC', 'RBC', 'PLATELET', 'CALCIUM', 'PROTEIN',
    }

    lines = []
    for i, result in enumerate(retrieved[:3]):
        meaningful = []
        for line in result['text'].split('\n'):
            line = line.strip()
            if len(line) > 10 and any(
                kw in line.upper() for kw in LAB_KEYWORDS
            ):
                meaningful.append(line)

        if meaningful:
            lines.append(f"[{i+1}] " + " | ".join(meaningful[:4]))

    if lines:
        return (
            "From your documents:\n\n"
            + "\n".join(lines)
            + "\n\n⚕ This is informational only. "
            "Please consult your healthcare provider."
        )

    # Last resort
    top = retrieved[0]['text'][:300] if retrieved else ''
    return (
        f"From your documents [1]: {top}...\n\n"
        "⚕ This is informational only. "
        "Please consult your healthcare provider."
    )


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
    # ── 1. Safety check ────────────────────────────────────────────────────
    safety = check_safety(question)
    if safety['triggered']:
        return {
            'answer': (
                f"⚠️ {safety['emergency_message']} "
                "Please call emergency services immediately "
                "(911 / 999 / 112). "
                "Do not rely on this tool in an emergency."
            ),
            'citations':         [],
            'safety_triggered':  True,
            'emergency_message': safety['emergency_message'],
            'retrieved':         [],
        }

    # ── 2. Ensure FAISS index ──────────────────────────────────────────────
    if not chunks:
        return {
            'answer': (
                "No documents are available for this session. "
                "Please upload a PDF and confirm the extracted text first."
            ),
            'citations':         [],
            'safety_triggered':  False,
            'emergency_message': None,
            'retrieved':         [],
        }

    ensure_index(session_id, chunks)

    # ── 3. Retrieve top-N chunks ───────────────────────────────────────────
    retrieved = retrieve_chunks(session_id, question, top_n=top_n)

    # ── 4. Citations-required policy ───────────────────────────────────────
    if not is_retrieval_sufficient(retrieved):
        return {
            'answer':            DONT_KNOW,
            'citations':         [],
            'safety_triggered':  False,
            'emergency_message': None,
            'retrieved':         retrieved,
        }

    # ── 5. Synthesize with Ollama ──────────────────────────────────────────
    answer = _call_ollama(question, retrieved)

    # ── 6. Build citations ─────────────────────────────────────────────────
    citations = []
    for i, result in enumerate(retrieved):
        chunk_idx   = result['chunk_index']
        chunk_db_id = (
            chunk_db_ids[chunk_idx]
            if chunk_idx < len(chunk_db_ids) else None
        )
        source_name = (
            source_names[chunk_idx]
            if chunk_idx < len(source_names) else 'Document'
        )
        citations.append({
            'label':      f"[{i + 1}]",
            'chunk_id':   chunk_db_id,
            'source_doc': source_name,
            'excerpt':    result['text'][:300],
        })

    return {
        'answer':            answer,
        'citations':         citations,
        'safety_triggered':  False,
        'emergency_message': None,
        'retrieved':         retrieved,
    }