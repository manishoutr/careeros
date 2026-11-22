"""Deterministic local text embeddings.

A learning-friendly choice: instead of calling an external embedding API we
build sparse bag-of-words vectors with the hashing trick. They are
deterministic (same text -> same vector, every run, no network), free, and
good enough to demonstrate vector similarity on a small catalogue.

Trade-off (documented in the README): hashed vectors capture lexical overlap,
not deep semantics. Swapping in a real embedding model means replacing
embed() and re-indexing; retrieval code only depends on cosine().
"""
import hashlib
import math
import re
from typing import List

DIM = 256
_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")

# Words that carry no retrieval signal. Filtering them in one place keeps
# BM25 idf and the hashed vectors clean of collisions on filler words.
STOPWORDS = {"a", "an", "the", "in", "on", "at", "of", "to", "for",
             "and", "or", "with", "using", "is", "are", "by", "from",
             "as", "our", "you", "your", "we", "will", "this", "that",
             "it", "its", "be", "used", "use"}


def tokenize(text: str) -> List[str]:
    """Lowercase word tokens, stopwords removed, with naive plural folding:
    'internships' also yields 'internship'. Deliberately simple - a stemmer
    dependency would do more, but this catches the common cases."""
    tokens = []
    for tok in _TOKEN_RE.findall((text or "").lower()):
        if tok in STOPWORDS:
            continue
        tokens.append(tok)
        if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 3:
            tokens.append(tok[:-1])
    return tokens


def embed(text: str) -> List[float]:
    vec = [0.0] * DIM
    for tok in tokenize(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))
