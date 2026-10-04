"""Optional local sentence embeddings with an explicit keyword fallback."""

import os
from pathlib import Path

from .settings import get_settings

_MODEL = None
_LOAD_ATTEMPTED = False


def _local_model():
    global _MODEL, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _MODEL
    _LOAD_ATTEMPTED = True
    model_path = os.environ.get("NWIS_EMBEDDING_MODEL", "").strip()
    if not model_path or not Path(model_path).exists():
        return None
    try:
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(model_path, local_files_only=True)
    except Exception:
        _MODEL = None
    return _MODEL


def available():
    model_path = os.environ.get("NWIS_EMBEDDING_MODEL", "").strip()
    if not model_path or not Path(model_path).exists():
        return False
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def encode_texts(texts):
    """Encode text locally for optional pgvector storage and reranking."""
    model = _local_model()
    if model is None or not texts:
        return None
    try:
        vectors = model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        if len(vectors.shape) != 2 or vectors.shape[1] != get_settings().vector_dimensions:
            return None
        return [[float(value) for value in vector] for vector in vectors]
    except Exception:
        return None


def encode_text(text):
    vectors = encode_texts([text])
    return vectors[0] if vectors else None


def similarities(query, texts):
    """Return cosine-like scores from a configured local model, or None."""
    model = _local_model()
    if model is None or not texts:
        return None
    try:
        vectors = model.encode([query] + list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return [float(value) for value in vectors[1:] @ vectors[0]]
    except Exception:
        return None
