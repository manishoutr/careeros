"""The evaluation harness runs and hybrid retrieval beats keyword-only."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_eval():
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "evaluate_ranking.py")],
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_hybrid_beats_keyword_baseline():
    out = _run_eval()
    lines = {ln.split()[0]: ln.split() for ln in out.splitlines()
             if ln.split() and ln.split()[0] in ("bm25", "vector", "weighted", "rrf")}
    assert set(lines) == {"bm25", "vector", "weighted", "rrf"}
    best_hybrid_ndcg = max(float(lines["weighted"][3]), float(lines["rrf"][3]))
    assert best_hybrid_ndcg >= float(lines["bm25"][3])
    for cols in lines.values():
        for v in cols[1:]:
            assert 0.0 <= float(v) <= 1.0
