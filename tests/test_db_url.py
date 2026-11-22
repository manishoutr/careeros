from app.db import _normalize_db_url


def test_postgres_urls_pinned_to_psycopg2():
    assert _normalize_db_url("postgresql://u:p@h/db").startswith("postgresql+psycopg2://")
    assert _normalize_db_url("postgres://u:p@h/db").startswith("postgresql+psycopg2://")
    assert _normalize_db_url("sqlite:///./x.db") == "sqlite:///./x.db"
    assert _normalize_db_url("postgresql+psycopg2://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
