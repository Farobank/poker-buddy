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
cp .env.example .env     # fill in ELEVENLABS_API_KEY + BUDDY_SHARED_SECRET
uv run pytest            # run the test suite (all green)
./scripts/start.sh       # backend + Cloudflare tunnel (writes BACKEND_URL to .env)
.venv/bin/python scripts/sync_agent.py   # create the ConvAI agent + 6 tools
./scripts/wire-agent.sh <agent-id>       # point the PWA at it (id printed above)
```

> **Heads-up lookups need a separate repo.** The HU (green-tier) engines route
> through a personal `hu-poker-trainer` Python repo that the shim imports at load.
> Without it, both `uv run pytest` and the backend fail to start; set
> `HU_TRAINER_PATH` in `.env` if you have it elsewhere. The 6-max preflop engine
> and theory lookup don't need it. (The LLM runs in ElevenLabs ConvAI, so no
> Anthropic key lives here — the model is chosen in the ElevenLabs dashboard.)

Open `frontend/index.html` (or deploy to GitHub Pages) and tap the widget.

**After a Mac sleep/restart:** `./scripts/relive.sh` brings the *same* agent back live in one command — no re-sync, no re-wire, no orphan agents. **Grade your sessions:** `.venv/bin/python scripts/grade_transcripts.py`.

## File layout

```
backend/
  main.py                  FastAPI app with 6 tool endpoints
  db.py                    SQLite schema + migrations
  grader.py                Transcript-grader core (flags ungrounded GTO numbers)
  engines/
    six_max_preflop.py     Grounded 6-max preflop ranges (published, SIX_MAX_NOTES.md)
  integrations/
    hu_trainer.py          Import shim for ~/hu-poker-trainer
  tools/
    confidence.py          green/yellow/amber tagging
    preflop_lookup.py      HU → hu_trainer; 6-max → six_max_preflop engine (grounded)
    postflop_lookup.py     HU flop c-bets → hu_trainer; turn/river/6-max → no-number read
    theory_lookup.py       BM25 over theory/*.md
    memory.py              read/write + opponent_profile_update
theory/                    Curated theory chunks for BM25
frontend/                  PWA shell (ElevenLabs widget)
tests/                     pytest suite + eval set
system-prompt.md           Paste-ready ConvAI system prompt
agent-config.json          Paste-ready ConvAI tool definitions
scripts/
  start.sh                 Launch backend + Cloudflare tunnel (writes BACKEND_URL)
  sync_agent.py            Create the ConvAI agent + 6 tools (fresh agent)
  update_agent.py          Update the LIVE agent in place — prompt + tool URLs, same id
  relive.sh                Post-restart: one command, no agent churn
  wire-agent.sh            Point the PWA at an agent id
  grade_transcripts.py     Pull ConvAI history → grade against the trust rule
```

## Status

v1 — built overnight 2026-05-27 → 2026-05-28.

## License

MIT — see [LICENSE](./LICENSE).
