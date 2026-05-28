# NEXT.md — pick up here

> Living status + next-steps doc. If you're a new Claude session opening this
> repo, **read [DESIGN.md](./DESIGN.md) first** for the why, then this for the
> what's-next. `WHILE_YOU_WERE_OUT.md` no longer exists (was session-specific,
> deleted before public push).

## Where we are (as of 2026-05-28)

v1 ships:

- ConvAI agent created via `scripts/sync_agent.py` (API, not dashboard)
- 6 webhook tools wired to backend, `X-Buddy-Secret` auth holds
- Frontend PWA serves through a Cloudflare quick tunnel
- 70 / 70 tests green (incl. the 10-spot eval suite in `tests/test_eval.py`)
- Public repo at https://github.com/Farobank/poker-buddy

Talking to it on a phone has worked. The agent calls the right tools for HU
spots, returns amber-with-honesty for 6-max preflop, and refuses real-time
online assistance per the boundary rule.

## Open issues

### 1. Postflop discipline leaks
The agent occasionally fabricates frequencies or sizings on postflop streets
the backend can't solve (HU turn/river → yellow; all 6-max postflop → amber).
The hard rule (`never state a GTO frequency without a tool call`) is in
`system-prompt.md` but isn't being enforced reliably under voice pressure.

**Fix path:** *not* more code. Tighten the system prompt:
- Move the trust rule earlier in the doc (it's currently under "Hard rules" #1, which is right, but it gets attenuated by the dense rules block under it).
- Add a vivid negative example: *"BAD: 'On the turn I'm betting about 60% here.' GOOD: 'On the turn I don't have direct solver data — my read is bet, but take it with a grain of salt.'"*
- After every postflop tool call that returns amber/yellow, re-state the confidence-language template inline.

A useful tool for finding the exact bad turns would be a **transcript grader** that pulls conversation history via ElevenLabs API and flags rule violations against the spec. ~30 min to build, dramatically faster than eyeballing. Skipped for now — single example from dogfooding is enough to start prompt iteration.

### 2. LLM stuck on Opus 4.7 (ElevenLabs gate)
Anthropic shipped Opus 4.8 (`claude-opus-4-8`). ElevenLabs ConvAI's enum still ends at `4-7`. Confirmed by 422 enum error on 2026-05-28 sync attempt. Retry in ~1 week; ElevenLabs usually whitelists new Anthropic models within days.

```python
# When ElevenLabs catches up, just flip this line in scripts/sync_agent.py
LLM_MODEL = "claude-opus-4-8"
```
Then `.venv/bin/python scripts/sync_agent.py` and `./scripts/wire-agent.sh <new-id>`.

### 3. Security hygiene (do before next public mention)
Two leaks happened in the original build session:
- `BUDDY_SHARED_SECRET` lived in a deleted doc that was briefly committed. History was rewritten + force-pushed, but orphan commits can persist on GitHub's side until their GC. **Mitigation:** rotate the secret + restart the tunnel (URL rotates, secret rotates, old combo is dead).
- `ELEVENLABS_API_KEY` was pasted in chat. **Mitigation:** delete in dashboard → create new → paste into `.env`.

Both 30-second tasks. See "Security rotation" section below for commands.

## Backlog (v2, not v1)

- Photo ingest — snap a hand-history screenshot, agent extracts the spot
- Hand-history file parsing (PokerStars/GG formats)
- Native iOS app if PWA UX caps out
- 6-max strategy engine (separate research project — weeks)
- Postflop solver integration via `~/poker_solver` (pre-solve common spots → local cache)
- Named Cloudflare tunnel (stable URL — no re-sync on every restart)
- Proactive leak surfacing (*"you've punted three river bets in 3-bet pots OOP this week"*)

## How to resume work

If the tunnels died (cmux closed, mac rebooted, etc.), bring them back:

```bash
# Backend + its tunnel
cd ~/projects/poker-buddy && ./scripts/start.sh

# Frontend + its tunnel (separate terminal)
cd ~/projects/poker-buddy/frontend && python3 -m http.server 5173 &
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5173
```

Each prints a new `*.trycloudflare.com` URL. Then re-sync the agent so its tool URLs point at the new backend tunnel:

```bash
# In .env, set BACKEND_URL=<new-backend-tunnel-url>
# Then:
cd ~/projects/poker-buddy && .venv/bin/python scripts/sync_agent.py
./scripts/wire-agent.sh <new-agent-id>
```

Then reload the PWA on the phone (it's a static page hitting the new agent).

## Security rotation

When you've stopped dogfooding for the day, or before any wider sharing:

```bash
# 1. Stop the tunnel + backend
pkill -f "cloudflared.*8765"
pkill -f "uvicorn backend.main"

# 2. Rotate the shared secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))" | \
  xargs -I{} sed -i '' "s|^BUDDY_SHARED_SECRET=.*|BUDDY_SHARED_SECRET={}|" ~/projects/poker-buddy/.env

# 3. Restart everything (gets a new tunnel URL too)
cd ~/projects/poker-buddy && ./scripts/start.sh &
# Wait ~15s for the URL to print, then re-sync:
.venv/bin/python scripts/sync_agent.py
./scripts/wire-agent.sh <new-agent-id>
```

For the ElevenLabs API key: delete the current one in
https://elevenlabs.io/app/settings/api-keys → create new → paste into `.env` at `ELEVENLABS_API_KEY=`.

## Key files for context

| File | Purpose |
|---|---|
| `DESIGN.md` | Source of truth for the architecture, rules, and rollout plan |
| `system-prompt.md` | The ConvAI agent's system prompt (paste-ready, no preamble) |
| `scripts/sync_agent.py` | One-shot agent + tools via ElevenLabs API |
| `scripts/wire-agent.sh` | Patch frontend with agent ID |
| `scripts/start.sh` | Boot backend + Cloudflare tunnel |
| `tests/test_eval.py` | 10 canonical spot tests + 3 discipline checks |
| `RUN_TOMORROW.md` | Manual ConvAI dashboard walkthrough (fallback if sync_agent breaks) |
| `agent-config.json` | Pre-API human-readable tool definitions (now superseded by sync_agent.py) |
| `.run/TOOLS_PASTE.md` | (gitignored) field-by-field paste recipe (also superseded) |

## What I'd do in the next session

In priority order:

1. **Verify the live agent still works.** Health-check both tunnels, do one voice round-trip. If anything's stale, re-sync.
2. **Pick the single most-annoying postflop leak from dogfooding** and rewrite the relevant chunk of `system-prompt.md` to close it. Re-sync. Re-test the same spot.
3. **Rotate security creds** (secret + ElevenLabs key) so nothing leaked is live.
4. **Build the transcript grader** if you want compounding leak-finding instead of one-at-a-time.
5. **Bump to Opus 4.8** the moment ElevenLabs whitelists it.
