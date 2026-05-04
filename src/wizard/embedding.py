"""Local embedding module — lazy-loads all-MiniLM-L6-v2 on first call.

Returns None instead of raising if sentence-transformers is not installed
or the model download fails, allowing callers to degrade gracefully.
"""

from __future__ import annotations

import logging
import struct
import threading

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_DIMS = 384

_model = None
_model_lock = threading.Lock()
_model_unavailable = False


def serialize_float32(vec: list[float]) -> bytes:
    """Pack a float list to the compact binary format sqlite-vec expects."""
    return struct.pack(f"{len(vec)}f", *vec)


def embed(text: str) -> list[float] | None:
    """Return a 384-dim float32 embedding, or None if model is unavailable."""
    global _model, _model_unavailable
    if not text or not text.strip():
        return None
    with _model_lock:
        if _model is None and not _model_unavailable:
            try:
                from sentence_transformers import SentenceTransformer
                _model = SentenceTransformer(_MODEL_NAME)
                logger.info("Loaded embedding model: %s", _MODEL_NAME)
            except Exception as e:
                logger.warning("Embedding model unavailable: %s", e)
                _model_unavailable = True
                return None
        if _model_unavailable:
            return None
    try:
        vec = _model.encode(text, convert_to_numpy=True).tolist()
        if len(vec) != _DIMS:
            logger.warning("Unexpected embedding dims: %d", len(vec))
            return None
        return vec
    except Exception as e:
        logger.warning("embed() failed: %s", e)
        return None
