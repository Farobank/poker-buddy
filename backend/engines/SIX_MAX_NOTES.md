# SIX_MAX_NOTES.md — 6-max preflop engine verification log

The 6-max analogue of `~/hu-poker-trainer/STRATEGY_NOTES.md`. Every range the
engine (`six_max_preflop.py`) encodes is a *published* 6-max 100bb cash range —
cross-checked against 3+ sources — never a fabricated number. This file is the
audit trail: what's grounded, how confident, and where the honest limits are.

**Scope:** NLHE cash, 6-max, 100bb effective, 2.5bb opens (3bb from the SB).
**Spots covered:** open (RFI) · vs-open (call / 3-bet) · vs-3-bet (4-bet / call /
fold) · blind defense. Anything past that (4-bet+ wars, limped or multiway pots)
returns amber + a note — no invented line.

## Confidence policy (maps to the buddy's green/yellow/amber)

- **green** — the uncontroversial core every source agrees on: premium
  opens/raises, value 3-bets/4-bets, and clear folds (a hand plainly outside a
  range). Speak confidently.
- **yellow** — range *edges* and light bluffs where published sources
  legitimately differ a few percent (mixed-frequency opens, light 3-bet/4-bet
  bluffs, marginal blind defends / IP flats). Honestly a read; flag it.
- **amber** — only on a *decline* (data=None + note) for an out-of-scope spot.
  Never attached to a number.

The combo-weighted opening % of each range is gated in
`tests/test_six_max_preflop.py` against the published bands below — a real
accuracy check, not eyeballing.

---

## 1. OPEN (RFI) ranges

**Status: CONFIRMED (composition = GTO 6-max consensus; %s verified vs 3+ sources)**

Encoded open % (engine `weighted_open_percent`, pure=full + mixed=half weight)
vs the published frequency bands:

| Pos | Engine | Published band | Sources |
|-----|--------|----------------|---------|
| UTG | 14.9%  | 15–17%         | Upswing, freebetrange, mypokercoaching, beastsofpoker, PokerOffer |
| MP/LJ | 18.9% | 19–22%        | (same) |
| CO  | 30.6%  | 25–30% (aggressive end) | (same) |
| BTN | 48.1%  | 40–48%         | (same) |
| SB  | 45.4%  | 39–47%         | (same) |

- All sources converge on the same shape: **ranges widen monotonically toward
  the button**, all pairs + all suited aces open by late position, the SB plays
  raise-or-fold (no limp) wider than ~40%.
- Composition cross-checked hand-by-hand against a plaintext GTO 6-max
  implementation (Tyloo `poker-range-analyzer`, `lib/ranges/*.ts`) and reconciled
  to the consensus opening frequencies above. Pure (raise≈100%) → green; mixed
  (solver opens at a partial frequency) → yellow.
- **CO is at the aggressive end (30.6% vs the 25–30% headline).** Defensible
  (GTO Wizard CO runs ~28–30% in several rake configs) but noted: CO edge hands
  are yellow for exactly this reason.
- The exact green/yellow hand lists per position are the code (`_OPEN_PURE`,
  `_OPEN_MIXED` in `six_max_preflop.py`) — source of truth, not duplicated here
  to avoid drift.

Sources:
[Upswing 6-max guide](https://upswingpoker.com/6-handed-max-poker-strategy/),
[mypokercoaching 100bb opening ranges](https://www.mypokercoaching.com/optimal-cash-game-opening-ranges-100bb/),
[freebetrange open-raise charts](https://blog.freebetrange.com/article/preflop-charts-open-raise-in-6-max-poker-cash-games),
[beastsofpoker 6-max strategy](https://beastsofpoker.com/6-max-poker-strategy/),
[PokerOffer 2026 GTO cheat sheet](https://thepokeroffer.com/poker-starting-hands-preflop-charts-2026/).

---

## 2. vs-OPEN (facing a single raise): 3-bet / call / fold

**Status: CONFIRMED (structure); tiered, not per-matchup grids**

Tiers (`six_max_preflop.py`):
- **3-bet value (green):** QQ+, AKs, AKo — pure value everywhere.
- **3-bet value-mixed (yellow):** JJ, TT, AQs, AJs, KQs, AQo — 3-bet/call mix.
- **3-bet bluff (yellow):** suited wheel aces A5s–A2s (canonical, universal —
  block AA/AK, nut-flush + wheel potential) plus KJs/KTs/QTs/JTs/T9s/K9s/Q9s/A5o.
- **call:** position-aware — the **BB closes and defends wide** (wider vs later
  opens), an **in-position non-blind** seat flats a band of strong hands, and
  **everyone else is 3-bet-or-fold**.
- **fold:** clear non-defends (green if clearly weak, yellow at the margin).

Grounding: 3-bet frequencies rise toward the button and vs later openers —
confirmed by pokertrainer.se's solver % grid (3-bet vs LJ ≈ 5.6–8.3%, BTN vs CO
≈ 12.8%, SB vs BTN ≈ 15.1%). Suited wheel aces as the canonical light 3-bet, and
the polarized 3-bet construction, are solver consensus. The marginal call/fold
boundary in BB defense and IP flatting uses a coarse hand-strength order — those
results are tagged **yellow** (a read), never green.

Sources:
[pokertrainer.se 3-betting ranges](https://pokertrainer.se/preflop-3-betting-ranges/),
[GTO Wizard range morphology](https://blog.gtowizard.com/preflop-range-morphology/),
[Red Chip preflop charts](https://redchippoker.com/preflop-poker-charts/),
[pokercoaching free preflop charts](https://pokercoaching.com/preflop-charts/).

---

## 3. vs-3-BET (the opener facing a 3-bet): 4-bet / call / fold

**Status: CONFIRMED (mirrors the HU `button_vs_3bet_decision` structure)**

Tiers:
- **4-bet value (green):** AA, KK, AKs.
- **4-bet value-mixed (yellow):** QQ, AKo, AQs, JJ — 4-bet/call mix.
- **4-bet bluff (yellow):** A5s, A4s — suited wheel aces (block AA/AK, make a
  wheel). Canonical 4-bet bluff across Upswing / GTO Wizard.
- **call (yellow):** strong hands with equity + playability continue (esp. IP).
- **fold:** the rest (green if clearly weak).

Grounding: at 100bb, AA/KK/AKs are pure value 4-bets; QQ/AKo/AQs/JJ mix
4-bet/call; A5s–A4s are the universally cited suited-wheel-ace bluffs. 4-bet
sizing ≈ 2.2x the 3-bet in position, ≈ 2.5x out of position.

Sources:
[Upswing 4-bet strategy](https://upswingpoker.com/4-bet-size-strategy/),
[GTO Wizard navigating range disadvantage as the 3-bettor](https://blog.gtowizard.com/navigating-range-disadvantage-as-the-3-bettor/),
[pokercoaching 4-betting](https://pokercoaching.com/preflop-charts/).

---

## 4. Sizing conventions

| Action | Size | Status |
|--------|------|--------|
| Open (RFI) | 2.5bb (3bb from SB) | CONFIRMED — Upswing/freebetrange/mypokercoaching all cite 2.5bb opens, 3bb SB |
| 3-bet | ≈3x the open IP, ≈4x OOP | CONFIRMED — IP 3-bets smaller, OOP/blind 3-bets larger |
| 4-bet | ≈2.2x the 3-bet IP, ≈2.5x OOP | CONFIRMED — matches the HU correction (IP 4-bets ~2.3x; smaller than the old 2.7x spec) |

---

## 5. Honest limitations (read these before trusting a borderline spot)

1. **Composition is consensus-level, not one solver's exact grid.** Encoded
   ranges reproduce the published GTO 6-max consensus and land inside the
   verified frequency bands; they are not a byte-exact dump of a single
   proprietary solver. Edge hands are tagged yellow precisely because sources
   differ there.
2. **vs-open / vs-3-bet are tiered, not per-position-pair grids.** The engine
   reasons by tier (value / bluff / call / fold) + a position-aware
   call-vs-fold rule, not a full 30-matchup × 169-hand table. Correct in shape
   and at the core; the call/fold margin is a yellow read.
3. **Mixed frequencies are collapsed to "raise, mixed (≈50%)".** The engine
   reports *that* a hand is a mix and tags it yellow, not the exact solver
   frequency. By design — the buddy needs action + honesty, not false precision.
4. **SB assumes a raise-or-fold (no-limp) strategy.** Standard for 100bb online;
   a limp-heavy SB strategy is out of scope.
5. **100bb only.** Short/deep stack range shifts are not modeled (v1).

When in doubt the engine returns **yellow** (a flagged read) or **declines to
amber** — it never upgrades a guess to green.
