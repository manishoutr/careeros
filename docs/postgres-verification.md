# PostgreSQL + pgvector verification

The app runs on SQLite by default (zero setup) and uses PostgreSQL + pgvector
when `DATABASE_URL` points at Postgres. This file records the evidence that
the Postgres path actually works, not just that the code exists.

## Method (2026-11-22)

Local real server: `pgserver` pip package (PostgreSQL 16.2, pgvector 0.6.2,
no docker/sudo required). The app was started with
`DATABASE_URL=postgresql://postgres:@/postgres?host=/tmp/pgsrv`.

Verified:

1. `init_db()` ran `CREATE EXTENSION IF NOT EXISTS vector` and created
   `job_vectors.embedding` as a real `VECTOR(384)` column
   (checked via `pg_attribute.atttypmod = 384`).
2. Seed ingest wrote 32 jobs into Postgres; embedding pass stored
   384-dim MiniLM vectors on each row (`embedding_model` recorded).
3. `vectorstore.sync_all()` populated `job_vectors`; pgvector SQL-side
   cosine shortlist (`ORDER BY embedding <=> :v`) returned the **identical
   top-5 job ids** as the in-Python full-scan cosine path for the probe
   query "backend engineer python fastapi postgres" (5/5 overlap).
4. End-to-end through FastAPI startup: `/api/health` reported
   `vectorstore: "pgvector"` and `embeddings.semantic: true`;
   `POST /api/search` returned ranked results; skill-gap and assistant
   endpoints worked against the same Postgres database.
5. Fresh-database path: all tables created from empty Postgres without
   manual DDL (migrations included).

Note: `fastapi.testclient.TestClient` must be used as a context manager
(or `init_db()` called explicitly) for startup init to run; a bare
`TestClient(app)` never fires startup events and the health endpoint then
reports the `python` fallback — that artifact caused a false alarm once.

## Production target

Neon free tier (no scheduled deletion) chosen over Render free Postgres
(1GB but self-destructs 30 days after creation) with user approval
(2026-11-22). Connection string is stored in the password vault, never in
the repo. Rollback: unset `DATABASE_URL` on the host to return to the
bundled SQLite path; `app/services/vectorstore.py` detects the backend and
disables pgvector cleanly.

## Hosted confirmation (2026-11-22, ~19:15 IST)

Render service careeros (srv-dc1dlnnf3r2c73ce7k50, Free/512MB, Singapore)
runs against the Neon database above. `/api/health`:
`db:"postgresql"`, `vectorstore:"pgvector"`, `embeddings.semantic:true`.
Hosted search, skill-gap and assistant flows exercised over HTTP; service
logs show clean startup (model download + pgvector init) and 200s with no
OOM restarts. Note: Render's memory/CPU graphs are paid-plan-only, so
memory-fit evidence is observed behavior (stable serving of all flows),
not a dashboard metric. First cutover deploy failed on SQLAlchemy 2.1's
new psycopg3 default; fixed by pinning postgresql+psycopg2 in app/db.py.
