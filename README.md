# Poker Buddy

Voice-first NLH cash poker discussion partner. Chill peer who happens to crush. Calls authoritative HU strategy from `hu-poker-trainer` for verified spots; reasons honestly from theory for 6-max with explicit confidence tagging.

**For the morning checklist, see [RUN_TOMORROW.md](./RUN_TOMORROW.md).**

For the full design, see [DESIGN.md](./DESIGN.md).

## What this is

A conversational layer over solver-grounded HU engines and theory-grounded 6-max reasoning. You call it on your phone walking home from a session, or open the web app at your desk to study. It remembers you across sessions.

## Architecture (one sentence)

ElevenLabs ConvAI agent (handles voice + Anthropic Opus 4.7) calls six tool webhooks on a local FastAPI backend, which routes HU spots through `~/hu-poker-trainer` and reasons-from-theory for 6-max.

## Quick start

```bash
uv sync                  # install deps into .venv
cp .env.example .env     # fill in ANTHROPIC_API_KEY etc.
uv run pytest            # verify everything passes
./scripts/start.sh       # run server + Cloudflare tunnel
```

Open `frontend/index.html` (or deploy to GitHub Pages) and tap the widget.

## File layout

```
backend/
  main.py                  FastAPI app with 6 tool endpoints
  db.py                    SQLite schema + migrations
  integrations/
    hu_trainer.py          Import shim for ~/hu-poker-trainer
  tools/
    confidence.py          green/yellow/amber tagging
    preflop_lookup.py      HU → hu_trainer; 6-max → null+amber
    postflop_lookup.py     same pattern
    theory_lookup.py       BM25 over theory/*.md
    memory.py              read/write + opponent_profile_update
theory/                    Curated theory chunks for BM25
frontend/                  PWA shell (ElevenLabs widget)
tests/                     pytest suite + eval set
system-prompt.md           Paste-ready ConvAI system prompt
agent-config.json          Paste-ready ConvAI tool definitions
scripts/start.sh           Launch backend + Cloudflare tunnel
```

## Status

v1 — built overnight 2026-05-27 → 2026-05-28.
