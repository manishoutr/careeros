"""Test environment, set before any app module reads its settings."""
import os

os.environ.setdefault("CAREEROS_DEMO_SEED", "1")   # API tests use the fictional demo catalogue
os.environ.setdefault("CAREEROS_AUTO_SYNC", "0")   # no background thread or network in tests
