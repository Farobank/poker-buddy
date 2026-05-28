# Poker Buddy — Design

> Voice-first NLH cash poker discussion partner. Chill peer who happens to crush.
> Conversational layer over solver-grounded HU engines (existing) and theory-grounded
> 6-max reasoning. Phone (PWA) + web, same agent across both.

**Status:** Design locked. Ready for implementation plan.
**Owner:** Bill
**Date:** 2026-05-27

---

## The Goal (verifiable)

**Ship v1 by end of weekend.**

### Acceptance criteria

- [ ] PWA installs to iPhone home screen, mic works
- [ ] Tap → ElevenLabs ConvAI agent picks up in <1s
- [ ] Sample HU hand discussion: "BTN open JTs, BB calls, K72r flop" → buddy delivers
      reasoning that (a) cites correct preflop range from hu-poker-trainer, (b) frames
      range advantage / board texture, (c) gives sizing recommendation, (d) sounds like
      Galfond-on-couch not a chatbot
- [ ] Sample 6-max hand discussion: same hand from CO instead of BTN → buddy reasons
      from theory, **explicitly flags lower confidence** (🟡), does NOT fabricate exact
      frequencies
- [ ] Buddy says "let me check the solver, two secs" before any HU lookup (verbal mask)
- [ ] Buddy never states a GTO frequency without a tool call (the trust rule)
- [ ] Memory persists across calls: tell it your stakes Monday, ask Tuesday, it remembers
- [ ] P50 response latency <1.5s end-to-end
- [ ] Cost <$15 for first week of dogfooding

Loop until all green.

---

## What's being built (one paragraph)

A voice-first conversational poker companion for NLH cash. You call it on your phone
(installed PWA) on the walk home from a session, or open the web app at your desk during
study. It listens, asks follow-ups, looks up authoritative HU strategy from your existing
`hu-poker-trainer` engines, reasons about 6-max from theory with honest confidence
tagging, remembers your stakes / opponents / leaks across sessions, and discusses hands
the way a sharp friend who plays your stakes would. No verdicts — discussion. No
fabricated GTO numbers — facts cite their source. Persona is Phil Galfond on a couch.

---

## Architecture

```
┌─────────────────────────────┐
│  PWA (install to home       │   Same code on phone + desk
│  screen — phone+desk)       │   ElevenLabs Convai widget (proven pattern
│                             │   from ~/projects/elevenlabs-talk-to-docs)
└──────────────┬──────────────┘
               │ WebRTC
               ▼
┌─────────────────────────────┐
│  ElevenLabs ConvAI Agent    │   Bundles VAD + STT + TTS (Flash 75ms)
│  ("Poker Buddy")            │   Native barge-in, turn-taking, semantic VAD
│  - voice: chill male        │   System prompt enforces persona + length + discipline
│  - LLM: Claude Opus 4.7     │   Adaptive thinking, effort: low (auto-escalates)
└──────────────┬──────────────┘
               │ HTTPS webhook (OpenAI-compatible custom LLM endpoint)
               ▼
┌─────────────────────────────┐
│  Backend (Python FastAPI    │   Stateless per-request, streams to ConvAI
│  on Mac, exposed via        │   Anthropic SDK with prompt caching enabled
│  Cloudflare Tunnel)         │   Tool definitions + tool dispatch
└──────────────┬──────────────┘
               │ tool dispatch
   ┌───────────┴─────────────────────────────────────────┐
   ▼           ▼               ▼              ▼          ▼
preflop_  postflop_     theory_lookup    memory_     opponent_
lookup    lookup        (BM25)           read/write  profile_
   │         │              │                │       update
   │         │              │                │           │
   ▼         ▼              ▼                ▼           ▼
HU? → hu-poker-trainer  curated      sessions.db (own copy, schema borrowed
6-max? → reasoning      theory       from hu-poker-trainer SM-2 + new
        (confidence:    chunks       buddy_profile, opponents, hand_journal tables)
        🟡)             (incl. STRATEGY_NOTES.md)
```

**Why this shape:**
- **PWA + Convai widget** is the proven pattern from `elevenlabs-talk-to-docs`. Reuse it.
- **Python backend** because `hu-poker-trainer` is Python. Direct import, no HTTP boundary
  for HU strategy. Fast.
- **Cloudflare Tunnel** exposes localhost backend to ElevenLabs webhook without
  deploying anywhere. Free, fast, reliable. v2 could move to Cloudflare Workers if
  needed.
- **Single LLM agent (not multi-agent)** because voice latency is the constraint —
  every sequential LLM call adds 400-800ms.

---

## LLM tier

- **Model:** `claude-opus-4-7`
- **Thinking:** `{type: "adaptive"}` — model decides per-turn. No `budget_tokens`.
- **Effort:** `output_config.effort = "low"` default. Adaptive thinking handles
  hard-spot escalation internally. Verbal "let me really think on this" command from
  user → escalate to `"high"` for study sessions.
- **Streaming:** Mandatory. Stream tokens to ConvAI within ~400ms TTFT.
- **Prompt caching:** Aggressive. System prompt block is ~5-10k tokens (persona + rules
  + tool descriptions + curated theory chunks). Cached with `cache_control`. 90% off
  on repeat hits → per-turn cost rounds to ~$0.003.
- **Max tokens:** 200 (≈ 30 sec spoken). Hard cap.

**System prompt outline** (full text in `system-prompt.md`):

```
You are a poker buddy. Specifically: a sharp friend who crushes NLH cash and is talking
to Bill about his hands. You are NOT a coach, tutor, or chatbot. You are a peer.

PERSONA
- Chill, conversational, sometimes profane. Will roast Bill for limping AJo UTG.
- Reasoning out loud, never delivering verdicts. "Hmm so on K72r BTN has range
  advantage..." not "The answer is to bet 33%."
- Reference Galfond's RIO style. Friendly wrapper. Elite substance.

HARD RULES
1. NEVER state a GTO frequency, sizing, or range from memory. Always call
   preflop_lookup or postflop_lookup. If the tool returns no data (e.g. 6-max), say
   "I don't have solver data for 6-max here; my read is X, take with grain of salt"
   and flag confidence (yellow/amber).
2. Before any slow tool call, verbally bookmark: "Let me check the solver, two secs..."
3. Spoken response under 30-60 words. No markdown, bullets, numbers as digits.
   Spell out: "G T O" not "GTO", "C bet" not "c-bet", "twenty-five percent" not "25%".
4. Discussion, not verdict. Frame the read first, then verify with tool.
5. Remember Bill across calls. Use memory_read at the start of any new session.
6. When the user describes a hand, extract the opponent profile if mentioned. Update
   opponent profile via opponent_profile_update.

TOOLS
- preflop_lookup(format, position, hand, stack_depth, action_so_far) → range + confidence
- postflop_lookup(format, board, position, line, stack_depth) → strategy + confidence
- theory_lookup(query, k=3) → cited theory chunks
- memory_read(topic) → buddy profile, recent leaks, opponents, recent hands
- memory_write(kind, content) → journal entry, consolidated nightly
- opponent_profile_update(label, observation) → incremental update

GREETING
Use this exact opener on the first call of a new session:
"What spot you got for me?"
```

---

## Tools (detailed)

### `preflop_lookup`

```python
def preflop_lookup(
    format: Literal["hu", "6max"],
    position: str,        # "btn", "bb", "co", etc.
    hand: str,            # "JTs", "AKo"
    stack_depth: int,     # in bb
    action_so_far: list   # e.g. ["btn_open_2.5", "bb_call"]
) -> dict:
    """
    HU: routes to hu-poker-trainer/src/preflop.py engine. Returns solver-verified
        range, action mix, confidence tag (🟢🟡🟠).
    6-max: returns None for range + confidence "amber"; agent must reason from theory.
    """
```

### `postflop_lookup`

```python
def postflop_lookup(
    format: Literal["hu", "6max"],
    board: str,           # "K72r"
    position: str,
    line: list,           # e.g. ["btn_cbet_33", "bb_call"]
    stack_depth: int,
) -> dict:
    """
    HU: routes to hu-poker-trainer/src/postflop.py + board.py. Returns c-bet
        frequency, sizing, board classification, confidence tag.
    6-max: returns None + amber confidence; agent reasons from theory.
    """
```

### `theory_lookup`

```python
def theory_lookup(query: str, k: int = 3) -> list[dict]:
    """
    BM25 over /theory corpus:
    - Curated chunks from Galfond / Run It Once, Polk / Upswing, Janda books
    - Plus STRATEGY_NOTES.md (the verification log from hu-poker-trainer)
    Returns top-k chunks with source citations.
    """
```

### `memory_read`

```python
def memory_read(topic: Literal[
    "profile", "recent_leaks", "opponents", "recent_hands", "session"
]) -> dict:
    """Returns Bill's buddy profile, scoped by topic to keep payload tight."""
```

### `memory_write`

```python
def memory_write(kind: Literal[
    "hand_discussed", "leak_identified", "opponent_observation", "session_note"
], content: dict) -> None:
    """Appends to hand_journal. Periodic consolidation runs nightly via cron."""
```

### `opponent_profile_update`

```python
def opponent_profile_update(label: str, observation: str) -> None:
    """
    label: Bill's own tag for the opponent ("the Russian reg", "Maria").
    observation: free-text update ("3-bets very wide from BTN").
    Stored in opponents table. Never linked to real online IDs.
    """
```

---

## Data model

SQLite at `~/projects/poker-buddy/buddy.db` (own copy; schema partly borrowed from
hu-poker-trainer's SM-2 patterns).

```sql
-- Bill's profile
CREATE TABLE profile (
    id INTEGER PRIMARY KEY,
    stakes TEXT,                    -- "$1/$2 6-max online, $2/$5 live"
    variants_json TEXT,             -- ["hu_cash", "6max_cash"]
    study_goals TEXT,
    updated_at INTEGER
);

-- Opponents (Bill's labels, never real IDs)
CREATE TABLE opponents (
    label TEXT PRIMARY KEY,
    profile_tags_json TEXT,         -- ["reg", "LAG", "3bets_wide_btn"]
    notes TEXT,
    last_seen INTEGER,
    hands_count INTEGER
);

-- Hands discussed
CREATE TABLE hands (
    id INTEGER PRIMARY KEY,
    format TEXT,                    -- "hu" or "6max"
    hand_text TEXT,                 -- "JTs"
    position TEXT,
    board TEXT,
    action_json TEXT,
    opponent_label TEXT,
    takeaway TEXT,                  -- buddy's summary of the spot
    confidence TEXT,                -- "green" / "yellow" / "amber"
    ts INTEGER
);

-- Sessions
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    started_at INTEGER,
    duration_sec INTEGER,
    hands_discussed INTEGER,
    summary TEXT
);

-- Leaks (Bill's recurring mistakes)
CREATE TABLE leaks (
    id INTEGER PRIMARY KEY,
    description TEXT,
    severity TEXT,                  -- "minor" / "real" / "bleeding"
    last_surfaced_at INTEGER,
    fix_status TEXT                 -- "open" / "working" / "fixed"
);

-- Raw journal — consolidated nightly into the structured tables
CREATE TABLE hand_journal (
    id INTEGER PRIMARY KEY,
    kind TEXT,
    content_json TEXT,
    ts INTEGER
);
```

Nightly consolidation cron (one Python script, runs via `launchd` or cron on the Mac)
reads `hand_journal`, calls Opus with a consolidation prompt, writes structured
updates back to the other tables.

---

## Confidence tags (the world-class discipline)

Every fact the buddy states has an implicit confidence level:

- **🟢 Green** — direct solver lookup from hu-poker-trainer (HU only)
- **🟡 Yellow** — theory-grounded reasoning with cited source (most 6-max answers,
  HU spots not yet covered in trainer engines)
- **🟠 Amber** — principle-only reasoning, no direct data
- **(no tag)** — conceptual discussion (range advantage, board texture, opponent reads).
  Doesn't need a tag because it's not a numeric claim.

Buddy verbally signals confidence on numeric claims: *"Solver says BTN opens about
sixty percent here, that's verified"* (green) vs. *"For 6-max I'd guess opening
around forty-eight percent from MP, but I'm not looking that up directly so take it
with a grain of salt"* (yellow).

---

## Failure modes & guardrails

| Failure | Mitigation |
|---|---|
| LLM states GTO numbers without tool call | Hard rule in system prompt + eval test |
| Solver tool returns slow (>5s) | Verbal fallback: "Solver's slow — my read is X, take with grain of salt" |
| ConvAI webhook timeout (>30s) | Stream "Let me think..." token within 1s to keep socket alive |
| iOS Safari mic permission denied | Onboarding screen in PWA with instructions |
| TTS char overage on Creator tier | Brevity rule in prompt (200 max tokens out) |
| Privacy leak (real opponent ID) | Hard rule: opponent labels are Bill's own tags only |
| Jargon mispronunciation ("GTO" → "guh-toh") | Replacement dict in TTS preprocessor + system prompt rule to spell out |
| Memory drift / wrong leaks | "Scratch that" command + manual correction in PWA |
| 6-max overconfidence | Hard rule: postflop_lookup returns "amber" for 6-max; buddy must say "I don't have solver data for this" |
| Bill plays a TOS-violating spot | Hard rule: buddy NEVER assists real-time during an active online hand |

---

## Testing & rollout

### Eval set (run on every deploy)
10 canonical hand-discussion spots, each with expected reasoning beats. End-to-end test
hits the webhook with a transcript and asserts the response against a checklist.

Spots cover:
1. HU BTN open standard hand (verify preflop_lookup called)
2. HU BB defense vs. small open (verify range cited correctly)
3. HU BTN c-bet on dry board (verify postflop_lookup, range-advantage framing)
4. HU BTN c-bet on wet board (verify smaller frequency, larger sizing)
5. 6-max CO open (verify confidence tag = yellow, no fabricated frequency)
6. 6-max 3-bet pot postflop (verify theory_lookup called for grounding)
7. Opponent profile update (mention "the Russian reg 3-bets wide", verify
   opponent_profile_update called)
8. Memory recall (cold-start: ask "what stakes do I play?" → recall from profile)
9. Leak surfacing (mention a spot similar to a past leak → buddy brings up the pattern)
10. Boundary test: "I'm in a hand right now online, what do I do?" → buddy refuses
    and explains why

### Live dogfood
Use it daily for 1 week. Daily journal note: what felt good, what felt fake, what
was wrong. Iterate.

### Polk-bar check
Pick 5 responses from the week. Honestly grade: "would Doug Polk respect this?"
Fix anything below 80% pass rate.

### Cost monitor
Track tokens/day, ConvAI minutes/day. Alert if >$1/day.

---

## Phasing

### v1 (this weekend) — ships when verify criteria green
- ElevenLabs ConvAI agent created in dashboard, configured with system prompt
- Python FastAPI backend with the 6 tools, imports hu-poker-trainer
- Cloudflare Tunnel exposing backend to ElevenLabs webhook
- PWA: single static page + ElevenLabs Convai widget (pattern from talk-to-docs)
- SQLite memory layer with the 6 tables
- BM25 theory index over ~30 curated chunks
- Eval suite of 10 spots
- Deployed on GitHub Pages (frontend) + Mac with Tunnel (backend)

### v2 (later) — when v1 has been used for 2+ weeks
- Photo ingest (snap a hand history screenshot)
- Hand-history file parsing (PokerStars/GG format → structured action input)
- Native iOS app if PWA UX is wanting
- 6-max engine work (separate research project — Upswing/Lucid charts, GTO Wizard
  data extraction, codify into Python engines like hu-poker-trainer did for HU)
- Postflop solver integration via ~/poker_solver (offline pre-solve common spots,
  cache to local DB)
- Leak-tracking proactive surfacing ("you've punted three river bets in 3-bet pots OOP
  this week — want to study that line?")

---

## Decision log

| # | Decision | Why |
|---|---|---|
| 1 | Voice-first poker buddy as the project | High joy + productivity. Voice is right modality for hand discussion. |
| 2 | NLH cash, mainly HU + 6-max, table-size flexible | Matches Bill's actual game. |
| 3 | All three moments (post-session, in-the-moment between-hands, study) | Want full companion. In-the-moment scoped to between-hands online or live; never real-time online. |
| 4 | Phase inputs: voice-first v1, multimodal v2 | Ship usable in a weekend. Learn from real use before deeper build. |
| 5 | Knowledge stack: solver-tool + RAG + reasoning LLM + opponent modeling | Noam Brown's research: LLMs need tool use + search; Pluribus's edge was opponent modeling on top of GTO. |
| 6 | Chill peer + world-class substance | Galfond's RIO style. Friendly wrapper, elite substance. |
| 7 | Phone (PWA) + Web, same agent | Covers all moments without native app. |
| 8 | Persistent profile + leak tracking | "Buddy who actually knows you" differentiator. |
| 9 | In-the-moment = between-hands online (not real-time during a hand) | Sites' TOS prohibit real-time assistance. Ethical scope. |
| 10 | Cost minimization: PWA over Twilio, hybrid Opus only with caching, BM25 not embeddings, local TexasSolver only when needed | Net new cost ~$0-10/mo realistic. |
| 11 | Path 1: separate poker-buddy project, HU calls hu-poker-trainer engines, 6-max is theory-grounded with honest confidence tags | Ships in 1-2 days. Engines pluggable. 6-max gap is transparent, not hidden. Building 6-max engines is a separate weeks-long research project that shouldn't block voice. |
| 12 | Backend: Python FastAPI on Mac via Cloudflare Tunnel (not Cloudflare Worker) | Direct import of hu-poker-trainer (Python). No HTTP boundary inside the hot path. Tunnel is free and reliable. Move to Workers if scaling. |
| 13 | LLM: single Opus 4.7 with adaptive thinking + low effort + caching (no Haiku router) | Voice latency budget can't afford 2 sequential LLM calls. Adaptive thinking + caching gets the cost win without the round-trip. |
| 14 | System prompt enforces: never state GTO numbers without tool call | This is the single rule that flips the agent from "confident bullshit" (PokerBench baseline) to trustworthy peer. |

---

## Assumptions (confirmed)

- Cost ceiling: $0-15/mo realistic. Sunk costs covered (GTO Wizard, ElevenLabs
  Creator, Claude Max). Only net new is potential Claude API overage and TTS overage
  if heavy use.
- Privacy: opponent labels are Bill's own tags only, never real online IDs.
- Backend: Python FastAPI on Mac, Cloudflare Tunnel exposes localhost to ElevenLabs.
- Voice: ElevenLabs default chill male voice for v1. Custom clone is v2+.

---

## Out of scope (explicit non-goals)

- Playing on Bill's behalf (no autonomous play)
- Real-time assistance during an active online hand (TOS violation)
- PLO, MTT, or mixed games (NLH cash only)
- Public product / multi-user (personal use)
- Native iOS app (v2+)
- Hand-history file parsing (v2)
- Photo/screenshot ingest (v2)
- Building 6-max strategy engines (separate research project)

---

## File layout (target)

```
~/projects/poker-buddy/
├── DESIGN.md                       (this file)
├── README.md
├── pyproject.toml
├── system-prompt.md                (the full ConvAI system prompt)
├── backend/
│   ├── main.py                     (FastAPI app, /api/buddy webhook)
│   ├── tools/
│   │   ├── preflop_lookup.py       (routes HU → hu-poker-trainer)
│   │   ├── postflop_lookup.py      (routes HU → hu-poker-trainer)
│   │   ├── theory_lookup.py        (BM25 over /theory/*.md)
│   │   ├── memory.py               (read/write + opponent_profile_update)
│   │   └── confidence.py           (green/yellow/amber tagging)
│   ├── llm.py                      (Anthropic SDK wrapper, caching, streaming)
│   ├── db.py                       (SQLite schema + migrations)
│   └── consolidation.py            (nightly cron entry point)
├── theory/                         (curated chunks for BM25)
│   ├── galfond-*.md
│   ├── polk-*.md
│   ├── janda-*.md
│   └── strategy-notes.md           (symlink to ~/hu-poker-trainer/STRATEGY_NOTES.md)
├── frontend/
│   ├── index.html                  (PWA shell + ElevenLabs Convai widget)
│   ├── manifest.json
│   ├── service-worker.js
│   └── icons/
├── tests/
│   ├── test_eval.py                (the 10 canonical eval spots)
│   ├── test_tools.py               (unit tests for each tool)
│   └── test_memory.py
└── buddy.db                        (created on first run)
```

---

*This is the source of truth for the design. Code that contradicts this doc should
be flagged in PR review. Update this doc when decisions change.*
