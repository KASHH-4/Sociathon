## Application structure
- Content routes render a shared TransitHear shell and view module so navigation and accessibility controls remain consistent.
- This is a frontend interactive prototype: label simulated data and integrations explicitly; never imply live transcription, verified facilities, ISL translation, or actual wearable connectivity without integration.
- Use global semantic design tokens for all visual roles, including facility statuses and transit alert colors, to preserve a consistent palette.
- Python Flask backend (`app.py` / `run.py`) serves the compiled SPA and PWA service worker with API simulation endpoints.
