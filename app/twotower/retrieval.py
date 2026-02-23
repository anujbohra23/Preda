"""
Two-tower retrieval using sentence transformers.

Tower 1 (query)    — patient intake text   → semantic embedding
Tower 2 (document) — disease description   → semantic embedding
Matching           — cosine similarity

Sentence transformers give semantic matching so "chest pain" matches
"cardiac pressure" and "myocardial discomfort" correctly.
"""
import os
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

from ..models import DiseaseCatalog


# ── Singleton model (shared with RAG to avoid loading twice) ──────────────────
_model: SentenceTransformer | None = None

def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        print("[TwoTower] Loading sentence transformer model...")
        _model = SentenceTransformer('all-MiniLM-L6-v2')
        print("[TwoTower] Model loaded.")
    return _model


# ── In-memory cache ────────────────────────────────────────────────────────────
_cache: dict = {
    'matrix': None,
    'ids':    None,
}


def _load_disease_matrix():
    """Load all disease embeddings from DB into numpy matrix. Cached."""
    if _cache['matrix'] is None:
        rows = DiseaseCatalog.query.all()
        if not rows:
            raise RuntimeError(
                'Disease catalog is empty. '
                'Run: python scripts/seed_disease_catalog.py'
            )
        ids     = []
        vectors = []
        for r in rows:
            if r.embedding_blob:
                ids.append(r.id)
                vec = np.frombuffer(r.embedding_blob, dtype=np.float32)
                vectors.append(vec)

        _cache['ids']    = ids
        _cache['matrix'] = np.stack(vectors)

    return _cache['matrix'], _cache['ids']


def clear_cache():
    _cache['matrix'] = None
    _cache['ids']    = None


# ── Embedding function ─────────────────────────────────────────────────────────

def _embed(text: str) -> np.ndarray:
    """Embed a single string. Returns normalised float32 vector."""
    model = get_model()
    vec   = model.encode(
        [text],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.array(vec, dtype=np.float32).flatten()


# ── Query builder ──────────────────────────────────────────────────────────────

def build_query_text(intake_fields: dict,
                     confirmed_chunks: list[str]) -> str:
    parts = []
    field_order = [
        'chief_complaint',
        'duration',
        'additional_notes',
        'medications',
        'allergies',
        'age',
        'sex',
    ]
    for field in field_order:
        value = intake_fields.get(field, '').strip()
        if value:
            if field == 'chief_complaint':
                parts.append(value)
                parts.append(value)   # weight it higher
            else:
                parts.append(value)

    for chunk in confirmed_chunks[:3]:
        parts.append(chunk[:500])

    return ' '.join(parts)


# ── Top-K retrieval ────────────────────────────────────────────────────────────

def retrieve_top_k(query_text: str, k: int = 10) -> list[dict]:
    if not query_text.strip():
        return []

    query_vec = _embed(query_text).reshape(1, -1)
    matrix, ids = _load_disease_matrix()

    scores      = cosine_similarity(query_vec, matrix).flatten()
    top_k_idx   = np.argsort(scores)[::-1][:k]

    results = []
    for rank, idx in enumerate(top_k_idx, start=1):
        disease_id = ids[idx]
        score      = float(scores[idx])
        disease    = DiseaseCatalog.query.get(disease_id)
        if disease:
            results.append({
                'disease_id':       disease_id,
                'disease_name':     disease.disease_name,
                'icd_code':         disease.icd_code or '',
                'short_desc':       disease.short_desc or '',
                'similarity_score': score,
                'rank':             rank,
            })

    return results


# ── Explainability ─────────────────────────────────────────────────────────────

_STOP_WORDS = {
    'the','a','an','and','or','of','in','is','are','with','to','from',
    'for','by','on','at','this','that','it','its','as','be','was','were',
    'has','have','had','not','but','can','may','also','which','who','when',
    'where','than','then','so','if','into','out','up','about','after',
    'before','between','through','during','causing','caused','due',
    'related','associated','including','symptoms','symptom','disease',
    'condition','disorder','syndrome','chronic','acute','severe',
    'mild','moderate',
}


def _tokenize(text: str) -> set[str]:
    tokens = set()
    for token in text.lower().split():
        token = token.strip('.,;:!?()[]"\'-')
        if len(token) > 3 and token not in _STOP_WORDS:
            tokens.add(token)
    return tokens


def explain_match(disease: dict,
                  intake_fields: dict,
                  confirmed_chunks: list[str]) -> dict:
    """
    Explainability via:
    1. Token overlap (keyword highlights)
    2. Per-field semantic similarity to disease
    """
    disease_text   = f"{disease['disease_name']} {disease['short_desc']}"
    disease_tokens = _tokenize(disease_text)

    query_text   = build_query_text(intake_fields, confirmed_chunks)
    query_tokens = _tokenize(query_text)
    matching     = list(disease_tokens & query_tokens)[:12]

    # Per-field semantic similarity
    disease_row = DiseaseCatalog.query.filter_by(
        disease_name=disease['disease_name']
    ).first()

    field_scores = {}
    if disease_row and disease_row.embedding_blob:
        disease_vec = np.frombuffer(
            disease_row.embedding_blob, dtype=np.float32
        ).reshape(1, -1)

        fields_to_score = [
            ('chief_complaint',  intake_fields.get('chief_complaint', '')),
            ('duration',         intake_fields.get('duration', '')),
            ('medications',      intake_fields.get('medications', '')),
            ('allergies',        intake_fields.get('allergies', '')),
            ('additional_notes', intake_fields.get('additional_notes', '')),
        ]

        for field_name, field_value in fields_to_score:
            if field_value and field_value.strip():
                fvec = _embed(field_value).reshape(1, -1)
                sim  = float(cosine_similarity(fvec, disease_vec)[0][0])
                if sim > 0:
                    field_scores[field_name] = sim

    total = sum(field_scores.values()) or 1.0
    field_contributions = {
        k: round((v / total) * 100, 1)
        for k, v in sorted(
            field_scores.items(), key=lambda x: x[1], reverse=True
        )
    }

    return {
        'matching_phrases':    matching,
        'field_contributions': field_contributions,
    }