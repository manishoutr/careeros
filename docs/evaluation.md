# Ranking evaluation

Corpus: seed/jobs.csv (32 fictional jobs). Judgements: tests/fixtures/eval_queries.json (12 queries, grades 0-2).

Reproduce: `python3 scripts/evaluate_ranking.py --write docs/evaluation.md`

| system | P@5 | R@10 | NDCG@10 |
| --- | --- | --- | --- |
| bm25 | 0.55 | 0.909 | 0.904 |
| vector | 0.617 | 0.981 | 0.933 |
| weighted | 0.583 | 0.981 | 0.961 |
| rrf | 0.6 | 0.921 | 0.933 |

## Per-query detail

| query | system | P@5 | R@10 | NDCG@10 |
| --- | --- | --- | --- | --- |
| python backend internship | bm25 | 0.8 | 0.778 | 0.824 |
| python backend internship | vector | 0.8 | 0.778 | 0.861 |
| python backend internship | weighted | 0.8 | 0.778 | 0.9 |
| python backend internship | rrf | 1.0 | 0.667 | 0.868 |
| react frontend internship | bm25 | 0.8 | 0.8 | 0.794 |
| react frontend internship | vector | 0.8 | 1.0 | 0.974 |
| react frontend internship | weighted | 0.8 | 1.0 | 0.967 |
| react frontend internship | rrf | 0.8 | 0.8 | 0.91 |
| machine learning intern | bm25 | 0.8 | 0.833 | 0.906 |
| machine learning intern | vector | 1.0 | 1.0 | 0.972 |
| machine learning intern | weighted | 0.8 | 1.0 | 0.971 |
| machine learning intern | rrf | 0.8 | 0.833 | 0.916 |
| devops cloud internship | bm25 | 0.4 | 0.5 | 0.695 |
| devops cloud internship | vector | 0.6 | 1.0 | 0.818 |
| devops cloud internship | weighted | 0.6 | 1.0 | 0.901 |
| devops cloud internship | rrf | 0.4 | 0.75 | 0.766 |
| data analyst internship sql | bm25 | 0.8 | 1.0 | 0.969 |
| data analyst internship sql | vector | 0.6 | 1.0 | 0.912 |
| data analyst internship sql | weighted | 0.8 | 1.0 | 0.99 |
| data analyst internship sql | rrf | 0.8 | 1.0 | 0.99 |
| android mobile developer intern | bm25 | 0.2 | 1.0 | 1.0 |
| android mobile developer intern | vector | 0.2 | 1.0 | 1.0 |
| android mobile developer intern | weighted | 0.2 | 1.0 | 1.0 |
| android mobile developer intern | rrf | 0.2 | 1.0 | 1.0 |
| qa testing automation internship | bm25 | 0.4 | 1.0 | 0.869 |
| qa testing automation internship | vector | 0.6 | 1.0 | 0.978 |
| qa testing automation internship | weighted | 0.4 | 1.0 | 0.954 |
| qa testing automation internship | rrf | 0.6 | 1.0 | 0.964 |
| security internship | bm25 | 0.2 | 1.0 | 1.0 |
| security internship | vector | 0.2 | 1.0 | 1.0 |
| security internship | weighted | 0.2 | 1.0 | 1.0 |
| security internship | rrf | 0.2 | 1.0 | 1.0 |
| remote backend internship | bm25 | 0.6 | 1.0 | 0.982 |
| remote backend internship | vector | 0.6 | 1.0 | 0.982 |
| remote backend internship | weighted | 0.6 | 1.0 | 0.982 |
| remote backend internship | rrf | 0.6 | 1.0 | 1.0 |
| nlp deep learning internship | bm25 | 0.6 | 1.0 | 0.984 |
| nlp deep learning internship | vector | 0.8 | 1.0 | 1.0 |
| nlp deep learning internship | weighted | 0.8 | 1.0 | 1.0 |
| nlp deep learning internship | rrf | 0.8 | 1.0 | 1.0 |
| java spring backend engineer | bm25 | 0.6 | 1.0 | 1.0 |
| java spring backend engineer | vector | 0.6 | 1.0 | 1.0 |
| java spring backend engineer | weighted | 0.6 | 1.0 | 1.0 |
| java spring backend engineer | rrf | 0.6 | 1.0 | 1.0 |
| full stack javascript internship | bm25 | 0.4 | 1.0 | 0.826 |
| full stack javascript internship | vector | 0.6 | 1.0 | 0.696 |
| full stack javascript internship | weighted | 0.4 | 1.0 | 0.872 |
| full stack javascript internship | rrf | 0.4 | 1.0 | 0.783 |
