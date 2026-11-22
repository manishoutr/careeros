"""Text embeddings.

Two backends, one interface:

* MiniLM (default): sentence-transformers/all-MiniLM-L6-v2 as a quantized
  ONNX model (~23 MB), downloaded from Hugging Face on first use into
  DATA_DIR/models. Produces normalized 384-dimensional vectors with real
  semantic similarity. No API key, no torch - onnxruntime only, so the free
  host's 512 MB memory limit still holds.
* Hashing (fallback): the original deterministic bag-of-words vectors,
  used when the ONNX model cannot be loaded (e.g. first run without
  network). Lexical overlap only; /api/health reports the active backend.

Every stored embedding records its model id (jobs.embedding_model) so a
model upgrade can find and re-embed stale rows (scripts/reindex.py).
"""
import hashlib
import logging
import math
import os
import re
import threading
from pathlib import Path
from typing import List, Optional

from ..config import settings

log = logging.getLogger("careeros.embeddings")

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")

# Words that carry no retrieval signal. Filtering them in one place keeps
# BM25 idf and the hashed vectors clean of collisions on filler words.
STOPWORDS = {"a", "an", "the", "in", "on", "at", "of", "to", "for",
             "and", "or", "with", "using", "is", "are", "by", "from",
             "as", "our", "you", "your", "we", "will", "this", "that",
             "it", "its", "be", "used", "use",
             "what", "which", "who", "whom", "whose", "when", "where",
             "why", "how", "do", "does", "did", "can", "could", "should",
             "would", "i", "me", "my", "he", "she", "they", "them", "his",
             "her", "their", "there", "here"}

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_VERSION = "minilm-l6-v2-onnx-q8"
MODEL_DIM = 384
_MODEL_FILES = ["onnx/model_quint8_avx2.onnx", "tokenizer.json"]

HASH_MODEL_VERSION = "hashing-v1"
HASH_DIM = 256


def tokenize(text: str) -> List[str]:
    """Lowercase word tokens, stopwords removed, with naive plural folding:
    'internships' also yields 'internship'. Used by BM25 and the hashing
    fallback; MiniLM tokenizes internally."""
    tokens = []
    for tok in _TOKEN_RE.findall((text or "").lower()):
        if tok in STOPWORDS:
            continue
        tokens.append(tok)
        if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 3:
            tokens.append(tok[:-1])
    return tokens


def _hash_embed(text: str) -> List[float]:
    vec = [0.0] * HASH_DIM
    for tok in tokenize(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % HASH_DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class _MiniLM:
    """Lazy singleton around the ONNX session and tokenizer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session = None
        self._tokenizer = None
        self._failed: Optional[str] = None

    def _model_dir(self) -> Path:
        return Path(settings.data_dir) / "models" / "all-MiniLM-L6-v2"

    def _load(self) -> None:
        model_dir = self._model_dir()
        onnx_path = model_dir / "onnx" / "model_quint8_avx2.onnx"
        tok_path = model_dir / "tokenizer.json"
        if not onnx_path.exists() or not tok_path.exists():
            model_dir.mkdir(parents=True, exist_ok=True)
            from huggingface_hub import hf_hub_download
            log.info("downloading %s (~23 MB, one time)", MODEL_NAME)
            for name in _MODEL_FILES:
                hf_hub_download(MODEL_NAME, name, local_dir=str(model_dir))
        import onnxruntime as ort
        from tokenizers import Tokenizer
        sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        tok = Tokenizer.from_file(str(tok_path))
        tok.enable_truncation(max_length=256)
        tok.enable_padding()
        self._session = sess
        self._tokenizer = tok

    def embed_batch(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Returns None when the model is unavailable; callers fall back."""
        if self._failed is not None:
            return None
        if os.getenv("CAREEROS_EMBEDDINGS", "").lower() == "off":
            self._failed = "disabled via CAREEROS_EMBEDDINGS=off"
            return None
        with self._lock:
            if self._session is None:
                try:
                    self._load()
                except Exception as e:  # no network on first run, disk, etc.
                    log.warning("MiniLM unavailable, using hashing fallback: %s", e)
                    self._failed = str(e)
                    return None
        import numpy as np
        out_all = []
        # Sub-batches cap peak memory: token embeddings for one sub-batch of
        # 32 at 256 tokens x 384 dims is ~12 MB, vs hundreds of MB if a full
        # ingest batch ran at once (that OOM-killed the 512 MB demo host).
        for start in range(0, len(texts), 32):
            part = [t or " " for t in texts[start:start + 32]]
            enc = self._tokenizer.encode_batch(part)
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            type_ids = np.array([e.type_ids for e in enc], dtype=np.int64)
            token_embeddings = self._session.run(
                None, {"input_ids": ids, "attention_mask": mask,
                       "token_type_ids": type_ids})[0]
            m = mask[..., None]
            pooled = (token_embeddings * m).sum(axis=1) / m.sum(axis=1)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            out_all.extend((pooled / norms).astype(float).tolist())
        return out_all


_minilm = _MiniLM()


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed many texts (internally sub-batched). Uses MiniLM when
    available, else hashing. A batch is homogeneous: never mixes models
    within one call."""
    vecs = _minilm.embed_batch(texts)
    if vecs is not None:
        return vecs
    return [_hash_embed(t) for t in texts]


def embed(text: str) -> List[float]:
    return embed_batch([text])[0]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def model_version() -> str:
    """The model id recorded on embeddings written right now."""
    return HASH_MODEL_VERSION if _minilm._failed else MODEL_VERSION


def backend_info() -> dict:
    return {"model": MODEL_NAME if _minilm._failed is None else "hashing (local fallback)",
            "version": model_version(),
            "dim": HASH_DIM if _minilm._failed else MODEL_DIM,
            "semantic": _minilm._failed is None}
