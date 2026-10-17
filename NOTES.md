# TransitHear — Design Notes and Decisions

## Decisions made under Conflict Rule (Rule 9)

### SSE and deployment
- Vercel serverless is **unsuitable** for SSE because each request spins a new process — in-process queues don't persist across requests. Use **Render** or **Railway** (both provide HTTPS, which phones require for microphone access) or run locally with an HTTPS tunnel (e.g. `ngrok http 5000`). The `Procfile` uses gunicorn with 1 worker + 8 threads (`-k gthread -w 1 --threads 8`) so the SSE broadcaster stays in-process. Decision: single-worker gunicorn over multi-worker to keep SSE queues coherent.

### Candidate set and LLM use
- The resolver uses **no LLM and no embeddings** for train matching. Exact-match + Levenshtein over digit strings is the right tool for 5-digit train numbers (12123 vs 12128). LLMs confuse similar numbers; deterministic edit-distance does not. Gemini is used only for language understanding (field extraction from messy speech) and recovery ranking — tasks where multilingual NLU matters.

### Only 5-digit runs for digit-word collapse
- Spoken-digit collapse (runs of ≥3) prevents "to" and "for" from becoming 2 and 4 in normal sentences. This trades off some recall on very short digit phrases (e.g. "platform 3" spoken as "three") for much better precision in mixed-language text. Platform numbers are extracted by a dedicated regex, not the digit-word collapse.

### MemoryRepo fallback
- If Supabase fails at startup, the app falls back to `MemoryRepo` seeded from `data/seed/*.json`. All demo features work without a database. `/api/health` reports `store_degraded: true` if the fallback is active.

### Seed data disclaimer
- All seed data is illustrative. Train numbers (12123, 12124, …, 12009) are real Indian Railways train identifiers; times, platforms, and facility status values are invented for the hackathon demo.

### Safety asymmetry (R5)
- Safety announcements are always shown, even at low confidence and even without a matched journey, because missing a safety alert costs more than a false one. This is intentional and documented in `reliability.py`.

## Setup order

1. Create a Supabase project at <https://supabase.com>.
2. In the SQL editor, run `supabase/schema.sql` (idempotent).
3. Copy `.env.example` to `.env` and fill in `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and optionally `GEMINI_API_KEY`.
4. `python scripts/seed_supabase.py` — loads seed data into Supabase.
5. `python run.py dev` — starts the development server on port 5000.
6. Open `http://localhost:5000/live` to use the live demo.

## 3-minute demo script

1. Open `/live` in Chrome on a phone or desktop.
2. Set journey: **route**, origin **CSMT**, destination **PUNE**. Click **Save journey**. Note candidate trains displayed.
3. Click **Simulate → Platform change**. Observe alert card with platform tile, trust badge, and haptic pattern in the JSON output.
4. Click **Simulate → Misrecognized number**. Observe "Heard 12126, matched to your train 12128. Please confirm." correction note.
5. Click **Simulate → Other train**. Observe `decision: ignore` — 12009 Shatabdi is not on the CSMT→PUNE corridor.
6. Click **Simulate → Safety alert**. Observe `alert_critical` even though confidence may be low (R5).
7. Click **Simulate → Noise**. Observe `decision: ignore` and verify no row added to history.
8. Open `/live/audit` in a new tab. See the decision summary and stage scores.
9. Click **Simulate official platform change** and re-run **Platform change** to see `confirmed by official feed (simulated)` in the trust badge.
10. Toggle **Haptic** off in Preferences; re-run a scenario; observe `haptic_pattern: []`.

## Known limitations

- Web Speech API is **Chrome, Edge, and Android browser only**. Firefox and Safari do not support it. iOS devices lack `navigator.vibrate`.
- Web Speech API requires the page to be **open and the screen to be on** (not just the PWA installed). Screen Wake Lock helps on Android.
- Phones require **HTTPS** for microphone access; use a tunnel for local development on mobile.
- The official Indian Railways feed is not connected — all `official_updates` are simulated.
- Gemini calls add ~2–6 s latency per announcement when enabled. Rules fallback is instant.
- The `supabase-py` and `google-generativeai` packages are optional; the app runs fully without them using `MemoryRepo` and the rules extractor.
