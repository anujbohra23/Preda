"""
Per-session FAISS vector store for RAG retrieval.
Uses sentence-transformers for semantic embeddings instead of TF-IDF.
This means questions like "what are my results?" correctly match
document text like "REPORT STATUS: FINAL" through semantic similarity.
"""

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ── Singleton model loader ─────────────────────────────────────────────────────
_model = None


def get_model() -> SentenceTransformer:
    """Load model once and cache it for the process lifetime."""
    global _model
    if _model is None:
        print("[RAG] Loading sentence transformer model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("[RAG] Model loaded.")
    return _model


# ── In-memory index cache: session_id → {index, chunks} ──────────────────────
_session_indexes: dict[int, dict] = {}


def build_session_index(session_id: int, chunks: list[str]) -> bool:
    """
    Embed all chunks with sentence transformer and build a FAISS index.
    Returns True on success, False if chunks is empty.
    """
    if not chunks:
        return False

    model = get_model()

    # Encode all chunks — returns (N, 384) float32 array
    embeddings = model.encode(
        chunks,
        normalize_embeddings=True,  # L2 normalise → cosine = dot product
        show_progress_bar=False,
        batch_size=32,
    )
    embeddings = np.array(embeddings, dtype=np.float32)

    dim = embeddings.shape[1]  # 384 for MiniLM
    index = faiss.IndexFlatIP(dim)  # inner product on normalised = cosine
    index.add(embeddings)

    _session_indexes[session_id] = {
        "index": index,
        "chunks": chunks,
    }
    return True


def retrieve_chunks(session_id: int, query: str, top_n: int = 5) -> list[dict]:
    """
    Retrieve top-N semantically similar chunks for a query.
    Returns list of { chunk_index, text, score }.
    """
    if session_id not in _session_indexes:
        return []

    store = _session_indexes[session_id]
    index = store["index"]
    chunks = store["chunks"]
    model = get_model()

    # Encode the query the same way
    q_vec = model.encode(
        [query],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    q_vec = np.array(q_vec, dtype=np.float32)

    k = min(top_n, len(chunks))
    scores, ids = index.search(q_vec, k)

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx >= 0:
            results.append(
                {
                    "chunk_index": int(idx),
                    "text": chunks[idx],
                    "score": float(score),
                }
            )

    return results


def invalidate_session(session_id: int):
    """Remove cached index for a session."""
    _session_indexes.pop(session_id, None)


def session_index_exists(session_id: int) -> bool:
    return session_id in _session_indexes
