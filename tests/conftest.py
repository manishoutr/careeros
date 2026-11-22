"""Test environment, set before any app module reads its settings."""
import os
import tempfile

os.environ.setdefault("CAREEROS_DEMO_SEED", "1")   # API tests use the fictional demo catalogue
os.environ.setdefault("CAREEROS_AUTO_SYNC", "0")   # no background thread or network in tests
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "tests.db")
