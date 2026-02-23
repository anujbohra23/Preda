"""
PDF text extraction and chunking.
Uses PyMuPDF (fitz) as primary extractor with pypdf as fallback.
"""
import os
import uuid
import fitz          # PyMuPDF
from pypdf import PdfReader
from werkzeug.utils import secure_filename


# ── Constants ──────────────────────────────────────────────────────────────────
CHUNK_SIZE   = 400   # words per chunk
CHUNK_OVERLAP = 80   # words overlap between chunks
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


# ── File saving ────────────────────────────────────────────────────────────────

def save_upload(file_storage, upload_folder: str,
                user_id: int, session_id: int) -> dict:
    """
    Validate and save an uploaded FileStorage object.
    Returns dict with stored_path, original_name, file_size_bytes, mime_type.
    Raises ValueError on validation failure.
    """
    original_name = secure_filename(file_storage.filename)

    if not original_name.lower().endswith('.pdf'):
        raise ValueError('Only PDF files are accepted.')

    # Read bytes to check size (file_storage.seek(0) after)
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)

    if size > MAX_FILE_BYTES:
        raise ValueError('File exceeds the 10 MB size limit.')

    if size == 0:
        raise ValueError('Uploaded file is empty.')

    # Build storage path: uploads/<user_id>/<session_id>/<uuid>.pdf
    dest_dir = os.path.join(upload_folder, str(user_id), str(session_id))
    os.makedirs(dest_dir, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}.pdf"
    stored_path = os.path.join(dest_dir, stored_filename)
    file_storage.save(stored_path)

    return {
        'original_name': original_name,
        'stored_path': stored_path,
        'file_size_bytes': size,
        'mime_type': 'application/pdf',
    }


# ── Text extraction ────────────────────────────────────────────────────────────

def extract_text_from_pdf(stored_path: str) -> str:
    """
    Extract raw text from a PDF file.
    Tries PyMuPDF first; falls back to pypdf if output is empty.
    """
    text = _extract_with_pymupdf(stored_path)
    if not text.strip():
        text = _extract_with_pypdf(stored_path)
    return text.strip()


def _extract_with_pymupdf(path: str) -> str:
    try:
        doc = fitz.open(path)
        pages = []
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        return '\n'.join(pages)
    except Exception:
        return ''


def _extract_with_pypdf(path: str) -> str:
    try:
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
        return '\n'.join(pages)
    except Exception:
        return ''


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_text(text: str,
               chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Split text into overlapping word-based chunks.
    Returns a list of chunk strings.
    """
    if not text.strip():
        return []

    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = ' '.join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start += chunk_size - overlap

    return chunks


def extract_and_chunk(stored_path: str) -> list[str]:
    """
    Full pipeline: extract text from PDF then chunk it.
    Returns list of chunk strings (may be empty if PDF has no text).
    """
    text = extract_text_from_pdf(stored_path)
    return chunk_text(text)