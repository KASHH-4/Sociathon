"""Shared pytest fixtures."""
import sys
import os
import pytest

# Add the Sociathon root to sys.path so `transithear` is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def memory_repo():
    """Fresh MemoryRepo seeded from data/seed/."""
    from transithear.db import MemoryRepo
    return MemoryRepo()


@pytest.fixture
def client(memory_repo, monkeypatch):
    """Flask test client wired to MemoryRepo with Gemini disabled."""
    # Ensure no Supabase or Gemini keys
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    # Force the global repo to our fresh MemoryRepo
    import transithear.db as db_module
    monkeypatch.setattr(db_module, "_repo", memory_repo)
    monkeypatch.setattr(db_module, "_store_degraded", False)

    # Also reset config flags
    import transithear.config as cfg
    monkeypatch.setattr(cfg, "SUPABASE_ENABLED", False)
    monkeypatch.setattr(cfg, "GEMINI_ENABLED", False)

    # Reset Gemini lazy client
    import transithear.extract_gemini as gem
    monkeypatch.setattr(gem, "_client", None)
    monkeypatch.setattr(gem, "_client_loaded", False)

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
