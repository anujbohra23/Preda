"""
Chunking utilities for RAG pipeline.
Reuses extractor logic but exposed separately so
the RAG pipeline can chunk any text, not just uploads.
"""

CHUNK_SIZE = 400
CHUNK_OVERLAP = 80


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """
    Split text into overlapping word-based chunks.
    Returns list of chunk strings.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start += chunk_size - overlap

    return chunks
