# AI Clarity Briefing

Real-time AI news briefing site with:

- Live feed aggregation from major AI sources
- Instant bullet-point digest on every visit
- Palette-themed interface optimized for quick scanning

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open: `http://127.0.0.1:5000`

## What it does

- Fetches feeds from official labs, research, and trusted publications.
- Creates a ready-to-read digest:
  - mission snapshot bullets
  - key moving themes
  - source highlights
  - feed health
- Displays latest headlines with summaries and source metadata.

## Notes

- Feed endpoints can change over time. If a source is down, it is listed under Feed Health.
- Add or remove feeds in `SOURCES` in `app.py`.
- The app supports both RSS/Atom feeds and HTML sources (AIxploria is configured as HTML parsing).
