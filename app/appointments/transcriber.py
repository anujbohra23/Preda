"""
Transcription using faster-whisper (local, no API key needed).
Model downloads ~150MB on first run, cached in ~/.cache/huggingface/
"""

import os

WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
# Options: tiny, base, small, medium, large
# base = good balance of speed and accuracy (~150MB)
# small = better accuracy (~500MB)

_whisper_model = None


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        print(f"[transcriber] Loading Whisper {WHISPER_MODEL_SIZE} model...")
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type="int8",  # efficient on CPU / Apple Silicon
        )
        print("[transcriber] Whisper model loaded.")
    return _whisper_model


def transcribe_audio(audio_path: str) -> dict:
    """
    Transcribe an audio file using faster-whisper.
    Returns { success, transcript, error }
    """
    if not os.path.exists(audio_path):
        return {
            "success": False,
            "transcript": "",
            "error": "Audio file not found.",
        }

    try:
        model = _get_model()
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=None,  # auto-detect language
        )

        transcript = " ".join(segment.text.strip() for segment in segments).strip()

        if not transcript:
            return {
                "success": False,
                "transcript": "",
                "error": (
                    "Transcription returned empty text. "
                    "The audio may be too quiet or contain no speech."
                ),
            }

        print(
            f"[transcriber] Detected language: {info.language} "
            f"({info.language_probability:.0%} confidence)"
        )
        return {"success": True, "transcript": transcript, "error": None}

    except Exception as e:
        return {"success": False, "transcript": "", "error": str(e)}


def whisper_available() -> bool:
    """
    Check if faster-whisper is importable.
    Always True if the package is installed.
    """
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False
