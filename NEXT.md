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

### Changed this session (2026-05-28, late) — 6-max preflop is now GROUNDED

- **6-max preflop engine shipped (was amber/None).** New `backend/engines/six_max_preflop.py`: open / vs-open (call·3bet) / vs-3bet (4bet·call·fold) / blind defense for all six seats (UTG, MP/LJ, CO, BTN, SB, BB) at 100bb, from published ranges (Upswing / GTO Wizard consensus, cross-verified — methodology + sources in `backend/engines/SIX_MAX_NOTES.md`). Tagged green/yellow, **never amber-guessing, never a fabricated number**; out-of-scope spots (4-bet+ wars, multiway) decline with amber + a note. Wired into `preflop_lookup.py` (`_six_max`), returns the same normalized `{data, confidence, source}` dict as the HU path.
- **System-prompt coverage map updated.** 6-max *preflop* is now grounded (green/yellow via `preflop_lookup`); 6-max *postflop* and HU turn/river remain no-number. Pushed live to `agent_8001ksqwswrme5s9kpvfw667t828`.
- **Theory corpus grew by 4 verified chunks** (HU turn play, bet-sizing theory, blockers/combinatorics, exploiting player types) under `theory/concept-*.md`, each with its verifier-flagged overclaims fixed. The 4 inaccurate chunks (HU river, 6-max preflop prose, 6-max postflop, multiway) were intentionally NOT merged.
- **`start.sh` tunnel-URL parse bug fixed** — it was grabbing `https://api.trycloudflare.com` (Cloudflare's control host, which also shows up in failed-tunnel error lines) instead of the real quick-tunnel URL. Now excludes `api.`.
- **Verified:** suite **144 green** (was 89). Pushed live + confirmed through the tunnel — "small blind heads up ace-king" → green; "six-max cutoff opening range" → green (not amber); wrong secret → 401.
- **Trust rule tightened after live grading.** The core held (every postflop turn flagged "no solver data, just my read"), but the buddy was tacking a pot fraction onto those reads ("like half pot", "a third pot") — a number it didn't look up. `system-prompt.md` now requires no-data reads to stay directional and number-free ("bet small", "go thin"); narrating the villain's bet is still fine. Pushed live.
- **Grader de-noised + now a reliable gate.** `backend/grader.py` no longer flags narrated villain bets ("he leads half pot") as fabrications (scoped villain-attribution guard) — the agent's own ungrounded sizing still flags. Validated on real transcripts. Suite now **146 green**.
- **Opus 4.8 still blocked (issue #2).** Re-probed the ElevenLabs enum 2026-05-28 — `claude-opus-4-8` still 400s (enum tops out at the older set). In-place PATCH would upgrade with no churn the moment it's whitelisted (no need for `sync_agent.py`'s recreate). Retry in ~a week.
- **Live now** via a backgrounded `start.sh` (tunnel `parenting-manufacturers-engagement-webcast` — ephemeral, dies on sleep/session-end; `relive.sh` brings it back). Branch `six-max-preflop-engine`, 3 commits, **not pushed** (your call).

### Changed this session (2026-05-28, evening)

- **Trust rule hardened in `system-prompt.md`.** Front-loaded a "one rule that matters most" block with BAD/GOOD example pairs that name the exact leak streets (HU turn/river + all 6-max postflop), and tightened Hard Rule #1 with the tool-coverage map. Closes issue #1's known failure mode. *Not yet live on the agent — gets pushed on the next `sync_agent.py` run.*
- **Transcript grader built** (`backend/grader.py` + `scripts/grade_transcripts.py`, 19 tests). Pulls ConvAI history and flags the critical violation — a frequency/sizing/percentage stated without a backing solver lookup — plus over-length and unspelled-digit slips. The compounding leak-finder from issue #1.
- **Resume loop de-footgunned.** `start.sh` now auto-writes the live tunnel URL to `BACKEND_URL` in `.env`; `sync_agent.py` now fails loudly if `BACKEND_URL` is missing instead of silently wiring tools to a dead hardcoded tunnel.
- **Backend restarted + verified live** through the tunnel: HU AKs → green w/ data, wrong secret → 401, 6-max → amber/no-data. Full suite 89/89 green.
- **Deferred (needs you):** the agent re-sync (it deletes+recreates the agent for an ephemeral tunnel) and the secret rotation (coupled to re-sync — see issue #3). One-command cycle in "What I'd do next."

**Grader caveat:** `normalize_transcript` reads the confirmed live fields (`role`, `message`, `tool_calls`, `tool_results`). The *inner* shape of `tool_results` (field names for tool name + result payload) is unconfirmed — no stored poker conversation has fired a tool yet (the only stored convos belong to `elevenlabs-talk-to-docs`). Re-validate grounding detection against the first real poker transcript that calls a lookup.

## Open issues

### 1. Postflop discipline leaks
The agent occasionally fabricates frequencies or sizings on postflop streets
the backend can't solve (HU turn/river → yellow; all 6-max postflop → amber).
The hard rule (`never state a GTO frequency without a tool call`) is in
`system-prompt.md` but isn't being enforced reliably under voice pressure.

**[Fixed in prompt 2026-05-28 — see "Changed this session" above. Re-sync to push it live; use the grader to catch regressions.]**

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

**Note (2026-05-28):** the shared secret is baked into the agent's tool configs at sync time, so rotating `BUDDY_SHARED_SECRET` only takes effect *after* a re-sync — rotate-then-`sync_agent.py` as one step (see "What I'd do next"). Local git history is clean (the leaked doc is gone, `.env` is gitignored); the only live exposures left are GitHub's orphan-commit GC window and the chat-pasted ElevenLabs key.

## Backlog (v2, not v1)

- Photo ingest — snap a hand-history screenshot, agent extracts the spot
- Hand-history file parsing (PokerStars/GG formats)
- Native iOS app if PWA UX caps out
- 6-max strategy engine (separate research project — weeks)
- Postflop solver integration via `~/poker_solver` (pre-solve common spots → local cache)
- Stable URL (named Cloudflare tunnel *needs a domain*, or ngrok's free static domain) → zero-command restart. `relive.sh` already makes restarts one command + churn-free, so this is just polish. Needs a domain or an ngrok account (your input).
- Proactive leak surfacing (*"you've punted three river bets in 3-bet pots OOP this week"*)

## How to resume work

After a Mac sleep / cmux close the trycloudflare URL changes. **One command brings the buddy back with no churn** — same agent id, no re-sync, no frontend re-wire, no orphan agents:

```bash
cd ~/projects/poker-buddy && ./scripts/relive.sh
```

It stops any stale backend+tunnel, boots a fresh one, and re-points the existing agent's tools at the new URL *in place* (`update_agent.py`). Verified end-to-end: agent id stays put, tools repoint, a live tool call returns green.

Edited `system-prompt.md` and just want to push the prompt to the live agent (backend already up)? Run `./scripts/update_agent.py` on its own.

Frontend PWA (separate, optional — the dashboard chat widget works without it):
```bash
cd ~/projects/poker-buddy/frontend && python3 -m http.server 5173 &
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:5173
```

**Only use `sync_agent.py` when you deliberately want a brand-new agent** (it deletes + recreates → new id → frontend re-wire → orphans). For normal restarts, `relive.sh` is the move.

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
| `scripts/start.sh` | Boot backend + Cloudflare tunnel (auto-writes BACKEND_URL) |
| `scripts/relive.sh` | **Post-restart: one command, no agent churn** (start + update in place) |
| `scripts/update_agent.py` | Update the LIVE agent in place — prompt + tool URLs, same id, self-verifying |
| `tests/test_eval.py` | 10 canonical spot tests + 3 discipline checks |
| `backend/grader.py` | Transcript grader core (pure; flags ungrounded numbers) |
| `scripts/grade_transcripts.py` | CLI: pull ConvAI history → grade → report |
| `RUN_TOMORROW.md` | Manual ConvAI dashboard walkthrough (fallback if sync_agent breaks) |
| `agent-config.json` | Pre-API human-readable tool definitions (now superseded by sync_agent.py) |
| `.run/TOOLS_PASTE.md` | (gitignored) field-by-field paste recipe (also superseded) |

## What I'd do in the next session

The agent is live and clean as of 2026-05-28: **`agent_8001ksqwswrme5s9kpvfw667t828`** — Opus 4.7, Eric voice, 6 tools on the live backend, hardened prompt (all verified via API). Churn is solved (`relive.sh`). What's left:

1. **Live-test the buddy** — the one thing not yet confirmed by a real conversation. If `curl -sf http://127.0.0.1:8765/health` fails (Mac slept), run `./scripts/relive.sh`. Then in the ElevenLabs dashboard chat on `agent_8001…` (Mock tools OFF), or the PWA: try a HU preflop (should cite real solver data) and a turn / 6-max spot (should say *"no solver data, my read is…"* — the fix in action).
2. **Grade it.** `.venv/bin/python scripts/grade_transcripts.py --limit 5` after talking to it. Zero critical = the trust rule held under real voice pressure. Re-validate the grader's grounding detection against the first transcript that actually fires a tool (caveat above).
3. **Dashboard cleanup.** Keep `agent_8001…`; delete the empty "Poker Buddy" `agent_4001ksqf…` and (if you're done with it) the talk-to-docs "My Agent". A few old tools may linger — force-delete in the Tools tab or ignore.
4. **Finish the key rotation.** The new ElevenLabs key is in `.env` and working, but the OLD key is still enabled in the dashboard — disable/delete it so the rotation counts. (Keep keys in `.env`, not chat.)
5. **Push** the local commits when ready (`git push`).
6. **Optional polish:** a stable URL (ngrok free static domain, or a Cloudflare domain) → *zero*-command restart. `relive.sh` already makes it one command + churn-free, so this is gravy.
7. **Opus 4.8** the moment ElevenLabs whitelists it (issue #2).
