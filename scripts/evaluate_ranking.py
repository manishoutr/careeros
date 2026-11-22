"""Ranking evaluation: P@5, Recall@10, NDCG@10 over a small labelled set.

Runs the four retrieval configurations against the seed catalogue and the
graded judgments in tests/fixtures/eval_queries.json:
  1. bm25       - keyword only
  2. vector     - embedding cosine only
  3. weighted   - min-max weighted hybrid (the original fusion)
  4. rrf        - Reciprocal Rank Fusion hybrid

Usage: python3 scripts/evaluate_ranking.py [--write docs/evaluation.md]
The point is not a high score; it is a reproducible number that shows
whether a change helps or hurts.
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.embeddings import embed, embed_batch  # noqa: E402
from app.services.retrieval import BM25, hybrid_scores, rrf_scores  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def precision_at_k(ranked_ids, relevant, k):
    return sum(1 for i in ranked_ids[:k] if i in relevant) / k


def recall_at_k(ranked_ids, relevant, k):
    return (sum(1 for i in ranked_ids[:k] if i in relevant) / len(relevant)) if relevant else 0.0


def ndcg_at_k(ranked_ids, grades, k):
    def dcg(ids):
        return sum(grades.get(i, 0) / math.log2(pos + 2) for pos, i in enumerate(ids[:k]))
    ideal = sorted(grades.values(), reverse=True)
    idcg = sum(g / math.log2(pos + 2) for pos, g in enumerate(ideal[:k]))
    return dcg(ranked_ids) / idcg if idcg else 0.0


def load_corpus():
    with open(ROOT / "seed" / "jobs.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    texts = [" ".join([r["title"], r["company"], r["location"],
                       (r.get("skills") or "").replace(";", " "),
                       r.get("description") or ""]) for r in rows]
    return rows, texts


def rank(ids, scores):
    return [i for _, i in sorted(zip(scores, ids), key=lambda t: t[0], reverse=True)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", default="", help="write a markdown report here")
    args = ap.parse_args()

    rows, texts = load_corpus()
    ids = list(range(1, len(rows) + 1))  # 1-based row ids matching the fixture
    embeddings = embed_batch(texts)
    fixtures = json.loads((ROOT / "tests" / "fixtures" / "eval_queries.json")
                          .read_text())["queries"]

    systems = ["bm25", "vector", "weighted", "rrf"]
    per_system = {s: {"p5": [], "r10": [], "ndcg10": []} for s in systems}
    detail_rows = []

    for fx in fixtures:
        q = fx["q"]
        grades = {int(k): v for k, v in fx["grades"].items()}
        relevant = set(grades)

        bm25_raw = BM25(texts).scores(q)
        qv = embed(q)
        vec_raw = [sum(a * b for a, b in zip(qv, e)) if len(e) == len(qv) else 0.0
                   for e in embeddings]
        weighted, _ = hybrid_scores(texts, embeddings, q, fusion="weighted")
        rrf = rrf_scores(bm25_raw, [max(0.0, v) for v in vec_raw])

        ranked = {"bm25": rank(ids, bm25_raw), "vector": rank(ids, vec_raw),
                  "weighted": rank(ids, weighted), "rrf": rank(ids, rrf)}
        for name in systems:
            r = ranked[name]
            p5 = precision_at_k(r, relevant, 5)
            r10 = recall_at_k(r, relevant, 10)
            n10 = ndcg_at_k(r, grades, 10)
            per_system[name]["p5"].append(p5)
            per_system[name]["r10"].append(r10)
            per_system[name]["ndcg10"].append(n10)
            detail_rows.append((q, name, round(p5, 3), round(r10, 3), round(n10, 3)))

    def avg(xs):
        return round(sum(xs) / len(xs), 3) if xs else 0.0

    print(f"Ranking evaluation over {len(fixtures)} labelled queries "
          f"({len(rows)} jobs, embedding model: see /api/health)\n")
    header = f"{'system':<10} {'P@5':>6} {'R@10':>6} {'NDCG@10':>8}"
    print(header + "\n" + "-" * len(header))
    lines = []
    for name in systems:
        m = {k: avg(v) for k, v in per_system[name].items()}
        lines.append(f"{name:<10} {m['p5']:>6} {m['r10']:>6} {m['ndcg10']:>8}")
        print(lines[-1])

    if args.write:
        out = ["# Ranking evaluation", "",
               f"Corpus: seed/jobs.csv ({len(rows)} fictional jobs). "
               f"Judgements: tests/fixtures/eval_queries.json "
               f"({len(fixtures)} queries, grades 0-2).", "",
               "Reproduce: `python3 scripts/evaluate_ranking.py --write docs/evaluation.md`",
               "", "| system | P@5 | R@10 | NDCG@10 |", "| --- | --- | --- | --- |"]
            # noqa: E501
        for name, line in zip(systems, lines):
            parts = line.split()
            out.append(f"| {parts[0]} | {parts[1]} | {parts[2]} | {parts[3]} |")
        out += ["", "## Per-query detail", "",
                "| query | system | P@5 | R@10 | NDCG@10 |", "| --- | --- | --- | --- | --- |"]
        for q, name, p5, r10, n10 in detail_rows:
            out.append(f"| {q} | {name} | {p5} | {r10} | {n10} |")
        Path(args.write).write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"\nwrote {args.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
