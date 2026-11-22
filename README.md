# CareerOS

An AI-powered career assistant, built as a learning project. Upload a resume,
search a job catalogue in natural language, get explainable recommendations,
chat with a grounded assistant, and generate a tailored resume draft you
review before using.

> Learning-project notes are inline across the codebase. This README explains
> what is built, why it is built that way, and what is deliberately left out.

## What it does (all working end to end)

1. **Resume parsing** - upload a PDF or TXT resume; the app extracts name,
   skills, experience and education into a structured profile you can correct.
2. **Job ingestion** - a seed CSV of 32 realistic India-focused jobs is
   normalized, deduplicated and indexed on startup.
3. **Hybrid search** - BM25 keyword scoring + vector cosine similarity,
   merged with min-max normalization.
4. **Explainable ranking** - every result is scored on four components
   (relevance, skills, location, experience) with human-readable reasons.
5. **Grounded assistant** - answers questions using only the candidate
   profile and job data, via bounded tool calls (`search_jobs`,
   `get_candidate_profile`).
6. **Resume tailoring** - builds a role-specific draft and logs every change
   with its source. A code-level validator rejects drafts that invent skills,
   employers or qualifications.

## Quickstart (5 minutes, no API key needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/make_sample_resume.py   # optional: creates a fake demo resume
python run.py                          # http://localhost:8000
```

Demo path:

1. Open http://localhost:8000, go to **Profile**, upload
   `sample_data/sample_resume.pdf` (or your own resume).
2. Go to **Jobs** and search `backend internships using Python in India`.
   Expand the score breakdown and reasons on each result.
3. Go to **Assistant** and ask "Which jobs fit my profile?".
4. Go to **Tailor**, pick a job, and review the change log.

Run the tests:

```bash
pip install -r requirements-dev.txt
pytest
```

## Claude integration

The app uses the Anthropic Messages API behind a single service layer
(`app/services/llm.py`). Set `ANTHROPIC_API_KEY` (see `.env.example`) and the
same features use Claude for extraction, tool-use chat and phrasing.

**Without a key the app runs in OFFLINE mode**: every feature still works
with deterministic local logic, and AI-looking output is labelled `offline`.
This is deliberate - it keeps the demo runnable anywhere and makes the tests
independent of a paid API.

Design rules enforced in code:

- Model output that gets saved is validated against pydantic schemas first;
  invalid output is discarded and the code falls back to deterministic logic.
- The API key never reaches the browser; the frontend only sees `mode`.
- The LLM never does work that SQL, search indexes or plain code do better.

## Architecture

```
app/
  main.py               FastAPI routes + reliability metrics
  config.py             environment-driven settings (DATABASE_URL, LLM_MODE, ...)
  db.py / models.py     SQLAlchemy setup; JSON stored as Text (SQLite & Postgres)
  schemas.py            API contracts; also validate Claude output
  services/
    embeddings.py       deterministic hashing embeddings (256-dim, no network)
    retrieval.py        BM25 + vector hybrid, min-max merged
    ranking.py          4-component explainable scoring with reasons
    parsing.py          PDF/TXT extraction + heuristic parser (+ Claude path)
    assistant.py        tool-use loop (Claude) / transparent offline rules
    tailor.py           draft builder + no-invention validator
    llm.py              the only file that talks to the Anthropic SDK
  static/               zero-build frontend (vanilla JS, served by FastAPI)
seed/jobs.csv           32-job demo catalogue
tests/                  parsing, retrieval, ranking, tailoring safety, API flow
```

Data storage defaults to SQLite (zero setup). Set
`DATABASE_URL=postgresql+psycopg2://...` to run on PostgreSQL; the same code
works on both. `docker-compose.yml` includes an optional `pgvector` profile.

## Engineering decisions worth explaining in an interview

- **Hashing embeddings instead of an embedding API.** Deterministic, free,
  testable offline; captures lexical overlap, not deep semantics. Swapping in
  a real embedding model means replacing `embed()` and re-ingesting.
- **Component scoring instead of one opaque rank.** The blueprint asks for
  transparent match explanations, so each component is scored separately and
  contributes a reason string. Weights are constants (`ranking.WEIGHTS`).
- **Safety enforced in code, not in a prompt.** `tailor.validate_draft`
  compares the draft against the profile; the API refuses to save a draft
  that invents anything. A prompt alone cannot guarantee that.
- **Everything asynchronous-looking is measured.** `/api/metrics` exposes
  request counts, errors, latency and pipeline counters.

## Known limitations (honest list)

- Offline resume parsing is heuristic; accuracy depends on resume formatting.
  That is why every parsed field is user-correctable, and why the Claude path
  exists. Field-level accuracy has been verified only on the sample resumes
  in `tests/` and `sample_data/`.
- The job catalogue is a 32-job seed CSV, not a live job board.
- Hashing embeddings will miss paraphrase-level matches a real embedding
  model would catch.
- No authentication: it is a single-candidate demo. Profile row id=1.
- Vector similarity is computed in Python. At catalogue scale (thousands of
  jobs) this is fine; at millions you would move similarity into pgvector.
