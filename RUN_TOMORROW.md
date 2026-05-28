# RUN_TOMORROW.md — Poker Buddy go-live checklist

> Saturday-morning, coffee in hand. ~30 minutes from "fresh laptop" to
> "talking to Buddy on the phone." Work top-to-bottom. Check each box.

---

## 0. Prereqs (one-time)

- [ ] `brew install uv cloudflared` (skip the ones you have)
- [ ] ElevenLabs account on Creator tier (or trial) → https://elevenlabs.io
- [ ] Anthropic API key with billing on → https://console.anthropic.com
- [ ] Mac stays awake during use: `caffeinate -d` in a spare terminal, or
      System Settings → Lock Screen → "Prevent automatic sleeping..." while plugged in.

## 1. Bootstrap the repo

```bash
cd ~/projects/poker-buddy
uv sync
cp .env.example .env
```

Fill in `.env`:

- [ ] `ANTHROPIC_API_KEY` — paste your sk-ant-... key
- [ ] `BUDDY_SHARED_SECRET` — generate a random string:
      `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
      Save it; you'll paste it into ElevenLabs in step 4.
- [ ] `HU_TRAINER_PATH` — confirm `~/hu-poker-trainer` exists. If you cloned
      it elsewhere, point it here.

Verify the tests are green before you go any further:

```bash
uv run pytest -q
```

Stop if anything is red. Fix first.

## 2. Launch backend + tunnel

```bash
./scripts/start.sh
```

You should see a banner with a `https://<random>.trycloudflare.com` URL.
**Copy it.** That's `BACKEND_URL` for the rest of this checklist.

- [ ] Sanity-check the tunnel responds:
      `curl https://<random>.trycloudflare.com/health` → `{"ok":true,...}`

Leave this terminal running. If you close it, the tunnel dies and ElevenLabs
loses its webhook target.

## 3. Create the ConvAI agent

In the ElevenLabs dashboard → **Conversational AI** → **Create Agent**:

- [ ] Name: `Poker Buddy`
- [ ] Language: English
- [ ] **System prompt:** paste the entire contents of `system-prompt.md`
- [ ] **First message:** `What spot you got for me?`
- [ ] **LLM:** Custom LLM → Anthropic → `claude-opus-4-7`
      - Extended thinking: **Adaptive**
      - Effort: **Low**
      - Max tokens: **250**
      - Prompt caching: **On**
- [ ] **Voice:** pick a chill male voice from your library
      (suggestion: Liam, voice ID `TX3LPaxmHKxFdv7VOQHJ`).
      Use **eleven_flash_v2_5** for low latency.

Don't save yet — tools come next.

## 4. Wire up the tools

Open `agent-config.json` in your editor. Find/replace:

- [ ] `{BACKEND_URL}` → your `https://<random>.trycloudflare.com` URL (no
      trailing slash). It appears in **six** tool URLs.
- [ ] `{BUDDY_SHARED_SECRET}` → the secret you generated in step 1.

Now in the ElevenLabs agent dashboard, under **Tools**, add one custom tool
per object in the `tools` array of `agent-config.json`. For each:

- [ ] Method: **POST**
- [ ] URL: copy from the JSON
- [ ] Headers: `Content-Type: application/json`, `X-Buddy-Secret: <secret>`
- [ ] Body schema: copy the `parameters` block verbatim
- [ ] Description: copy from the JSON

Six tools total: `preflop_lookup`, `postflop_lookup`, `theory_lookup`,
`memory_read`, `memory_write`, `opponent_profile_update`.

- [ ] Save the agent. Note the **Agent ID** — you'll need it in step 5.

## 5. Wire up the PWA frontend

```bash
# In a separate terminal — don't touch the one running start.sh.
$EDITOR ~/projects/poker-buddy/frontend/index.html
```

- [ ] Replace `REPLACE_WITH_YOUR_AGENT_ID` (line ~159) with your Agent ID.

Serve the frontend locally for the first smoke test:

```bash
cd ~/projects/poker-buddy/frontend
python3 -m http.server 5173
```

- [ ] Open `http://localhost:5173` in your laptop browser.
- [ ] You should see "What spot you got for me?" headline and the
      ElevenLabs widget bottom-center.
- [ ] Click the widget. Allow mic. Say:
      *"BTN open ace king suited heads up, hundred big blinds."*
- [ ] You should hear back something like: *"Yeah, ace king suited, button,
      hundred big. Let me check the solver, one sec..."* followed by a raise
      recommendation. **If you hear a frequency without a tool call latency, stop.**
      The trust rule is broken — re-check the system prompt is fully pasted.

## 6. Install on iPhone

Two options. Pick one.

### Option A — Quick (use the tunnel directly)

The Cloudflare quick tunnel only exposes the backend on port 8765, not the
frontend. To install the PWA from your phone, use a second tunnel:

```bash
# In a third terminal.
cd ~/projects/poker-buddy/frontend
python3 -m http.server 5173 &
cloudflared tunnel --url http://127.0.0.1:5173
```

Copy the second `*.trycloudflare.com` URL onto your phone (AirDrop or Notes).

- [ ] iPhone Safari → open the URL.
- [ ] Share sheet → **Add to Home Screen** → name "Buddy".
- [ ] Open the new home-screen icon. Tap the widget. Allow mic.
- [ ] Say: *"What's our spot? Let's talk a BB call."* — confirm round-trip works.

### Option B — Ship it (deploy frontend to GitHub Pages)

Only do this once the agent ID is wired in. The frontend has no secrets.

```bash
cd ~/projects/poker-buddy
gh repo create poker-buddy --public --source=. --remote=origin --push
gh repo edit --enable-pages --pages-branch=main --pages-path=/frontend
```

Wait ~60s, then visit `https://<your-gh-user>.github.io/poker-buddy/`.

- [ ] Add to iPhone home screen as in Option A's last three checkboxes.

> Note: the backend tunnel URL still rotates each time you re-run start.sh.
> If you want a stable URL, set up a named Cloudflare Tunnel later. Not v1's
> problem.

## 7. The acceptance bar

These come straight from DESIGN.md — don't skip them.

- [ ] PWA installs to iPhone home screen, mic works.
- [ ] Tap → ConvAI agent picks up in <1s.
- [ ] **HU sample:** *"BTN open JTs, BB calls, K72 rainbow flop"* — buddy
      cites preflop range, frames range advantage, gives sizing, sounds like
      Galfond not a chatbot.
- [ ] **6-max sample:** same hand from CO instead of BTN — buddy **explicitly
      flags amber/yellow** and does NOT fabricate a frequency.
- [ ] Buddy verbalises *"let me check the solver, two secs"* before any HU
      lookup.
- [ ] Buddy never states a GTO frequency without a tool call (the trust rule).
- [ ] Memory persists: in conversation, say *"I play one-two six-max"*.
      End the call. Start a new call. Ask *"what stakes do I play?"* — buddy
      recalls.
- [ ] P50 response latency feels <1.5s end-to-end.

Anything red? Don't ship. Loop until all green.

## 8. First-week dogfood ritual

- [ ] Use it daily for one week. Each day, jot in `~/research/buddy-week-1.md`:
      what felt good, what felt fake, what was wrong.
- [ ] **Polk-bar check** at the end of the week: pick 5 responses. Honestly
      grade *"would Doug Polk respect this?"* Fix anything below 80% pass rate.
- [ ] **Cost monitor:** `uv run python -m backend.consolidation --cost-report`
      (if you implement it) or eyeball Anthropic usage. Alert if >$1/day.

## 9. When the tunnel rotates

Quick tunnels get a new URL on every restart. Every time you re-run
`start.sh`:

- [ ] Update the six tool URLs in the ElevenLabs agent dashboard with the new
      `BACKEND_URL`. Annoying — that's why a named tunnel is on the v2 list.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Buddy hangs after first sentence | Tunnel rotated or `start.sh` not running | Restart `./scripts/start.sh`, update agent tool URLs |
| Buddy invents a 6-max frequency | System prompt got truncated when pasted | Re-paste `system-prompt.md` in full |
| Mic doesn't work on iPhone | Permission denied | iOS Settings → Safari → Camera & Microphone → Allow; or delete + re-add the home-screen app |
| `start.sh` says "cloudflared not found" | Homebrew install missed | `brew install cloudflared` |
| Tests fail on `hu_trainer` import | `HU_TRAINER_PATH` wrong in `.env` | Confirm path; `ls $HU_TRAINER_PATH/src` should show the module |
| 401 from tool endpoint in production | `X-Buddy-Secret` header missing or wrong | Re-check the header in every ElevenLabs tool config |

---

## When you're done

- [ ] Stop `start.sh` (`Ctrl-C`) when you're not using it — saves API spend.
- [ ] If you change the system prompt, re-run `uv run pytest tests/test_eval.py`
      before re-pasting into ElevenLabs. The eval suite catches drift.

Good hands.
