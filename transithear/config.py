"""Configuration: env loading, feature flags, thresholds."""
import os
from dotenv import load_dotenv

load_dotenv()

# External service credentials
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Feature flags
SUPABASE_ENABLED: bool = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
GEMINI_ENABLED: bool = bool(GEMINI_API_KEY)

# Reliability thresholds
THRESH_ALERT: float = float(os.environ.get("THRESH_ALERT", "0.75"))
THRESH_VERIFY: float = float(os.environ.get("THRESH_VERIFY", "0.50"))
DEDUPE_SECONDS: int = int(os.environ.get("DEDUPE_SECONDS", "60"))

# Input safety
MAX_TRANSCRIPT_CHARS: int = int(os.environ.get("MAX_TRANSCRIPT_CHARS", "1000"))
RATE_LIMIT_PER_MIN: int = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))

# Server
PORT: int = int(os.environ.get("PORT", "5000"))

# Simulation flags
SIMULATED_OFFICIAL_FEED: bool = os.environ.get("SIMULATED_OFFICIAL_FEED", "true").lower() in ("1", "true", "yes")
