"""Grounded 6-max preflop ranges engine (100bb cash).

This is the 6-max analogue of ~/hu-poker-trainer/src/preflop.py. It encodes
standard *published* 6-max ranges (Upswing / GTO Wizard consensus, cross-checked
against a plaintext GTO implementation and the published opening-frequency
bands) so the buddy can talk about a 6-max preflop spot with real data instead
of guessing. Provenance, sources, and the green/yellow methodology are logged in
SIX_MAX_NOTES.md — the same "verify against 3+ sources" discipline as the HU
engine's STRATEGY_NOTES.md.

The trust contract (mirrors the HU path):
  - Every SUPPORTED spot (open / vs-open / vs-3bet / blind defense) returns a
    decision tagged ``green`` or ``yellow`` with real data. We NEVER return
    amber and NEVER fabricate a frequency: a hand outside a range is a green
    fold; a borderline/mixed hand is a yellow, explicitly-flagged mix.
  - Spots OUTSIDE the v1 grounded set (facing a 4-bet, multiway, limped pots)
    decline honestly via ``lookup`` with ``data=None`` + a note — no invented
    line.

Confidence policy:
  - ``green``  — the uncontroversial core every source agrees on (premium
    opens/raises, value 3-bets/4-bets, clear folds).
  - ``yellow`` — borderline/mixed hands where published sources legitimately
    differ (range edges, light 3-bet/4-bet bluffs, marginal defends). Honestly
    a *read*, surfaced as such.

Returned dict shape is byte-for-byte the HU contract from
``hu_trainer._serialize_preflop``: ``{data: {...}, confidence, source}`` (+ a
``note`` on declines), so the tool layer treats HU and 6-max identically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.tools.confidence import Confidence

# --- Sizing (published 6-max 100bb conventions; see SIX_MAX_NOTES.md §4) ---
_OPEN_SIZE_BB = 2.5
_SB_OPEN_SIZE_BB = 3.0
_THREE_BET_IP_MULT = 3.0   # 3-bet ~3x the open when in position
_THREE_BET_OOP_MULT = 4.0  # ~4x out of position (blinds, OOP cold 3-bet)
_FOUR_BET_IP_MULT = 2.2    # 4-bet ~2.2x the 3-bet in position
_FOUR_BET_OOP_MULT = 2.5   # ~2.5x out of position


# ---------------------------------------------------------------------------
# Hand notation helpers
# ---------------------------------------------------------------------------

_RANK_ORDER = "23456789TJQKA"
_RANK_VAL = {r: i + 2 for i, r in enumerate(_RANK_ORDER)}  # '2'->2 ... 'A'->14
_SUIT_CHARS = set("cdhs")


def normalize_hand(raw: str) -> str:
    """Canonicalize a hand to range notation: 'AA', 'AKs', 'AKo'.

    Accepts range notation ('JTs', 'AKo', order-insensitive) OR concrete cards
    ('JhTh', 'AhKs', 'AhAs'). High card first, suited/offsuit suffix preserved.
    """
    s = raw.strip().replace("10", "T").replace(" ", "")
    if not s:
        raise ValueError(f"empty hand: {raw!r}")

    def _rank(c: str) -> str:
        u = c.upper()
        if u not in _RANK_VAL:
            raise ValueError(f"invalid card rank {c!r} in hand {raw!r}")
        return u

    # Concrete cards: 4 chars, positions 1 & 3 are suit chars (e.g. 'AhKs').
    if len(s) == 4 and s[1].lower() in _SUIT_CHARS and s[3].lower() in _SUIT_CHARS:
        r1, su1 = _rank(s[0]), s[1].lower()
        r2, su2 = _rank(s[2]), s[3].lower()
        if r1 == r2:
            return f"{r1}{r2}"
        hi, lo = (r1, r2) if _RANK_VAL[r1] >= _RANK_VAL[r2] else (r2, r1)
        return f"{hi}{lo}{'s' if su1 == su2 else 'o'}"

    # Pocket pair as 'AA'.
    if len(s) == 2 and s[0].upper() == s[1].upper():
        return f"{_rank(s[0])}{_rank(s[0])}"

    # Range notation 'AKs' / 'AKo' (order-insensitive).
    if len(s) == 3 and s[2].lower() in ("s", "o"):
        r1, r2 = _rank(s[0]), _rank(s[1])
        if r1 == r2:
            return f"{r1}{r2}"
        hi, lo = (r1, r2) if _RANK_VAL[r1] >= _RANK_VAL[r2] else (r2, r1)
        return f"{hi}{lo}{s[2].lower()}"

    raise ValueError(f"unrecognized hand notation: {raw!r}")


def _combos(notation: str) -> int:
    """Combo count for a hand class: pair=6, suited=4, offsuit=12."""
    if len(notation) == 2:
        return 6
    return 4 if notation.endswith("s") else 12


def _score(notation: str) -> int:
    """Coarse RAW preflop hand strength (high-card weighted). Used ONLY for the
    marginal call/fold boundary when FACING A 3-BET, where raw equity vs a
    strong, capped-ish 3-bet range matters more than postflop playability.

    Clear value/fold cases are handled by explicit green sets; this just orders
    the fuzzy middle the way every source agrees it orders (high cards, pairs,
    suitedness, connectedness)."""
    if len(notation) == 2:  # pair
        return 40 + _RANK_VAL[notation[0]] * 4  # 22->48, AA->96
    hi = _RANK_VAL[notation[0]]
    lo = _RANK_VAL[notation[1]]
    suited = notation.endswith("s")
    s = hi * 4 + lo * 2
    if suited:
        s += 8
    gap = hi - lo - 1
    s -= gap * 2
    return s


def _defense_score(notation: str) -> int:
    """Playability-weighted hand order for DEFENDING / FLATTING decisions (BB
    defense, in-position flats). Unlike `_score`, this prizes the qualities that
    realize equity heads-up postflop — suitedness and connectedness — over raw
    high-card strength, because that's what makes a hand worth continuing rather
    than folding to a single raise.

    Why a separate scorer: a single high-card-weighted score ranked offsuit junk
    (96o, K7o) ABOVE suited connectors (54s, 65s), so BB defense came out
    backwards (folding 54s while calling 96o). Defending and 4-bet-or-folding
    want opposite orderings, so they get different scorers (boil-the-lake fix).

    Pairs are always strong defends/flats (set value), so they score high."""
    if len(notation) == 2:  # pair — always a strong continue
        return 50 + _RANK_VAL[notation[0]] * 4
    hi = _RANK_VAL[notation[0]]
    lo = _RANK_VAL[notation[1]]
    suited = notation.endswith("s")
    gap = hi - lo - 1
    s = hi * 2 + lo * 3  # weight the low card (connectedness) more than the high card
    if suited:
        s += 24
        if gap == 0:
            s += 8       # true connectors
        elif gap == 1:
            s += 4       # one-gappers
        else:
            s -= gap * 2
    else:
        s -= 6           # offsuit hands realize worse heads-up
        s -= gap * 3     # offsuit gappers are the genuine junk
    return s


# ---------------------------------------------------------------------------
# Range construction helpers (generate sets from rules to cut transcription error)
# ---------------------------------------------------------------------------

def _pairs_from(low: str) -> set[str]:
    """All pairs >= low, e.g. _pairs_from('7') -> {'77','88',...,'AA'}."""
    return {r + r for r in _RANK_ORDER if _RANK_VAL[r] >= _RANK_VAL[low]}


def _suited_with(high: str, lowest: str) -> set[str]:
    """Suited combos high-x for x from `lowest` up to just below `high`.
    e.g. _suited_with('A','2') -> all suited aces A2s..AKs."""
    return {
        f"{high}{r}s"
        for r in _RANK_ORDER
        if _RANK_VAL[lowest] <= _RANK_VAL[r] < _RANK_VAL[high]
    }


def _offsuit_with(high: str, lowest: str) -> set[str]:
    return {
        f"{high}{r}o"
        for r in _RANK_ORDER
        if _RANK_VAL[lowest] <= _RANK_VAL[r] < _RANK_VAL[high]
    }


# ---------------------------------------------------------------------------
# OPEN (RFI) ranges by position — pure (green) vs mixed (yellow) edges.
# Composition follows the GTO 6-max 100bb consensus (see SIX_MAX_NOTES.md §1);
# combo-weighted % verified against published bands in tests.
# ---------------------------------------------------------------------------

_OPEN_PURE: dict[str, set[str]] = {
    "utg": (
        _pairs_from("6")
        | _suited_with("A", "T") | {"KQs", "KJs", "KTs", "QJs", "QTs", "JTs", "T9s"}
        | {"AJo", "AQo", "AKo", "KQo"}
    ),
    "mp": (
        _pairs_from("5")
        | _suited_with("A", "9") | _suited_with("K", "9") | {"QJs", "QTs", "Q9s", "JTs", "J9s", "T9s", "98s"}
        | {"ATo", "AJo", "AQo", "AKo", "KJo", "KQo"}
    ),
    "co": (
        _pairs_from("2")
        | _suited_with("A", "2") | _suited_with("K", "8")
        | {"QJs", "QTs", "Q9s", "JTs", "J9s", "T9s", "T8s", "98s", "97s", "87s", "76s", "65s", "54s"}
        | _offsuit_with("A", "8") | {"KQo", "KJo", "KTo", "QJo", "QTo", "JTo"}
    ),
    "btn": (
        _pairs_from("2")
        | _suited_with("A", "2") | _suited_with("K", "5") | _suited_with("Q", "6") | _suited_with("J", "7")
        | {"T9s", "T8s", "T7s", "98s", "97s", "96s", "87s", "86s", "76s", "75s", "65s", "64s", "54s", "53s"}
        | _offsuit_with("A", "2") | _offsuit_with("K", "8")
        | {"QJo", "QTo", "Q9o", "JTo", "J9o", "T9o", "T8o", "98o", "87o"}
    ),
    "sb": (
        _pairs_from("2")
        | _suited_with("A", "2") | _suited_with("K", "5") | _suited_with("Q", "6") | _suited_with("J", "7")
        | {"T9s", "T8s", "T7s", "98s", "97s", "87s", "86s", "76s", "75s", "65s", "64s", "54s", "53s"}
        | _offsuit_with("A", "5") | _offsuit_with("K", "9")
        | {"QJo", "QTo", "Q9o", "JTo", "J9o", "T9o", "98o", "87o"}
    ),
}

_OPEN_MIXED: dict[str, set[str]] = {
    "utg": (
        _pairs_from("2") - _pairs_from("6")
        | _suited_with("A", "2") - _suited_with("A", "T")
        | {"K9s", "Q9s", "J9s", "98s", "87s", "76s"}
        | {"ATo", "KJo"}
    ),
    "mp": (
        {"22", "33", "44"}
        | _suited_with("A", "2") - _suited_with("A", "9")
        | {"K8s", "Q8s", "J8s", "T8s", "87s", "76s", "65s"}
        | {"A9o", "KTo", "QJo"}
    ),
    "co": (
        {"K7s", "Q8s", "J8s", "T7s", "86s", "75s", "64s", "53s"}
        | {"A7o", "A6o", "A5o", "K9o", "Q9o", "J9o", "T9o", "98o"}
    ),
    "btn": (
        {"K4s", "K3s", "K2s", "Q5s", "Q4s", "J6s", "T6s", "95s", "85s", "74s", "63s", "43s"}
        | {"K7o", "K6o", "Q8o", "J8o", "T7o", "97o", "76o", "65o"}
    ),
    "sb": (
        {"K4s", "K3s", "K2s", "Q5s", "Q4s", "Q3s", "J6s", "J5s", "T6s", "96s", "85s", "74s", "63s", "43s"}
        | {"A4o", "A3o", "A2o", "K8o", "K7o", "Q8o", "J8o", "T8o", "97o", "76o", "65o", "54o"}
    ),
}


# ---------------------------------------------------------------------------
# vs-OPEN tiers (facing a single raise): 3-bet value / mixed / bluff, then
# position-aware call vs fold. See SIX_MAX_NOTES.md §2.
# ---------------------------------------------------------------------------

_3BET_VALUE = {"QQ", "KK", "AA", "AKs", "AKo"}                 # pure value, green
_3BET_VALUE_MIXED = {"JJ", "TT", "AQs", "AJs", "KQs", "AQo"}   # 3-bet/call mix, yellow
# Light 3-bets (yellow). Primary = suited wheel aces: 3-bet from any seat,
# including the BB. Secondary = suited broadways/connectors: 3-bet IP or from the
# SB, but FLAT from the BB (closing the action cheaply, these realize equity
# better as calls than as 3-bets).
_3BET_BLUFF_PRIMARY = {"A5s", "A4s", "A3s", "A2s"}
_3BET_BLUFF_SECONDARY = {"KJs", "KTs", "QTs", "JTs", "T9s", "K9s", "Q9s", "A5o"}

# ---------------------------------------------------------------------------
# vs-3BET tiers (the original raiser facing a 3-bet): 4-bet value / mixed /
# bluff, then call vs fold by strength. Mirrors HU button_vs_3bet_decision.
# ---------------------------------------------------------------------------

_4BET_VALUE = {"AA", "KK", "AKs"}              # pure value, green
_4BET_VALUE_MIXED = {"QQ", "AKo", "AQs", "JJ"}  # 4-bet/call mix, yellow
_4BET_BLUFF = {"A5s", "A4s"}                    # suited wheel-ace 4-bet bluffs, yellow

_SEAT_ORDER = {"utg": 0, "mp": 1, "co": 2, "btn": 3, "sb": 4, "bb": 5}
_POSITION_ALIASES = {
    "lj": "mp", "lojack": "mp", "hj": "mp", "hijack": "mp", "mp1": "mp", "mp2": "mp",
    "ep": "utg", "button": "btn", "bu": "btn", "smallblind": "sb", "bigblind": "bb",
    "co": "co", "utg": "utg", "mp": "mp", "btn": "btn", "sb": "sb", "bb": "bb",
}


def _canon_pos(pos: str) -> str:
    p = pos.lower().strip()
    return _POSITION_ALIASES.get(p, p)


# ---------------------------------------------------------------------------
# Decision dataclass — same fields the HU PreflopDecision exposes, so the
# serializer produces an identical `data` dict.
# ---------------------------------------------------------------------------

@dataclass
class SixMaxDecision:
    action: str                 # "fold" | "call" | "raise" | "3bet" | "4bet"
    frequency: float
    is_mixed: bool
    alternative: str | None
    alt_frequency: float
    sizing_bb: float | None
    principle: str
    confidence: Confidence
    explanation: str


def _decision(
    action: str,
    confidence: Confidence,
    principle: str,
    explanation: str,
    *,
    frequency: float = 1.0,
    is_mixed: bool = False,
    alternative: str | None = None,
    alt_frequency: float = 0.0,
    sizing_bb: float | None = None,
) -> SixMaxDecision:
    return SixMaxDecision(
        action=action,
        frequency=frequency,
        is_mixed=is_mixed,
        alternative=alternative,
        alt_frequency=alt_frequency,
        sizing_bb=sizing_bb,
        principle=principle,
        confidence=confidence,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# OPEN decision
# ---------------------------------------------------------------------------

def open_decision(position: str, hand: str) -> SixMaxDecision:
    """RFI (raise-first-in) decision for a 6-max position at 100bb."""
    pos = _canon_pos(position)
    h = normalize_hand(hand)
    if pos not in _OPEN_PURE:
        raise ValueError(f"no open range for position {position!r}")
    size = _SB_OPEN_SIZE_BB if pos == "sb" else _OPEN_SIZE_BB
    label = pos.upper()

    if h in _OPEN_PURE[pos]:
        return _decision(
            "raise", Confidence.GREEN, "Position-based RFI",
            f"{h} is a standard {label} open at one hundred big. Raise to "
            f"{size:g} big blinds.",
            sizing_bb=size,
        )
    if h in _OPEN_MIXED[pos]:
        return _decision(
            "raise", Confidence.YELLOW, "RFI range edge (mixed)",
            f"{h} sits on the edge of the {label} opening range — solvers open it "
            f"at a mixed frequency, so it's a fine open but not automatic. Raise to "
            f"{size:g} big blinds.",
            frequency=0.5, is_mixed=True, alternative="fold", alt_frequency=0.5,
            sizing_bb=size,
        )
    return _decision(
        "fold", Confidence.GREEN, "Position-based RFI",
        f"{h} is outside the {label} opening range at one hundred big. Fold.",
    )


# ---------------------------------------------------------------------------
# vs-OPEN decision
# ---------------------------------------------------------------------------

def vs_open_decision(position: str, hand: str, opener: str) -> SixMaxDecision:
    """Decision facing a single open: 3-bet / call / fold.

    Position-aware: the BB closes the action and defends very wide; an in-position
    non-blind seat can flat strong hands; everyone else is 3-bet-or-fold."""
    pos = _canon_pos(position)
    opp = _canon_pos(opener)
    h = normalize_hand(hand)
    hero_ip = pos in ("mp", "co", "btn") and _SEAT_ORDER.get(pos, 9) > _SEAT_ORDER.get(opp, -1)
    tbet_size = round(_OPEN_SIZE_BB * (_THREE_BET_IP_MULT if hero_ip else _THREE_BET_OOP_MULT), 1)

    # --- 3-bet value (green) ---
    if h in _3BET_VALUE:
        return _decision(
            "3bet", Confidence.GREEN, "Linear/polarized 3-bet (value)",
            f"{h} is a pure value three-bet versus a {opp.upper()} open. "
            f"Three-bet to about {tbet_size:g} big.",
            sizing_bb=tbet_size,
        )
    # --- 3-bet value mixed (yellow) ---
    if h in _3BET_VALUE_MIXED:
        return _decision(
            "3bet", Confidence.YELLOW, "3-bet-or-call mix (value)",
            f"{h} is a three-bet-or-call mix versus a {opp.upper()} open — strong "
            f"enough to three-bet for value, fine as a flat too. Leaning three-bet "
            f"to about {tbet_size:g} big.",
            frequency=0.5, is_mixed=True, alternative="call", alt_frequency=0.5,
            sizing_bb=tbet_size,
        )
    # --- 3-bet bluff (yellow) ---
    # Primary (wheel aces) 3-bet from any seat; secondary suited broadways 3-bet
    # in position or from the SB, but flat from the BB (fall through to call).
    if h in _3BET_BLUFF_PRIMARY or (h in _3BET_BLUFF_SECONDARY and pos != "bb"):
        alt = "call" if (hero_ip or pos == "bb") else "fold"
        ace_blocker = h.startswith("A") and h.endswith("s")
        return _decision(
            "3bet", Confidence.YELLOW, "Light 3-bet (bluff)",
            f"{h} works as a light three-bet versus a {opp.upper()} open — "
            f"{'suited wheel ace, blocks their value and has nut-flush potential' if ace_blocker else 'good blockers and playability if called'}. "
            f"My read leans three-bet to about {tbet_size:g} big, but {alt} is fine.",
            frequency=0.5, is_mixed=True, alternative=alt, alt_frequency=0.5,
            sizing_bb=tbet_size,
        )

    # --- calling / folding (playability-weighted; these are reads → yellow) ---
    score = _defense_score(h)
    if pos == "bb":
        # BB closes the action and defends wider vs later (looser) opens. Suited
        # connectors are the canonical defends, weak offsuit one-gappers fold.
        thresh = {"utg": 56, "mp": 50, "co": 44, "btn": 34, "sb": 32}.get(opp, 44)
        if score >= thresh:
            return _decision(
                "call", Confidence.YELLOW, "Big-blind defense",
                f"{h} defends from the big blind versus a {opp.upper()} open — "
                f"you're closing the action and getting a price, so call and play it "
                f"out of position. (My read on the defending range, not a solver pull.)",
            )
        return _decision(
            "fold", Confidence.GREEN if score < thresh - 14 else Confidence.YELLOW,
            "Big-blind defense",
            f"{h} is below the big-blind defending range versus a {opp.upper()} open. Fold.",
        )

    # Pocket pairs flat IN POSITION to set-mine — uncontroversial at 100bb.
    if hero_ip and len(h) == 2:
        return _decision(
            "call", Confidence.YELLOW, "In-position flat (set-mine)",
            f"{h} flats a {opp.upper()} open in position to set-mine — the implied "
            f"odds are great at a hundred big when you flop a set. (My read, not a "
            f"solver pull.)",
        )

    if hero_ip and score >= 50:
        return _decision(
            "call", Confidence.YELLOW, "In-position flat",
            f"{h} flats a {opp.upper()} open in position — too good to fold, not "
            f"strong enough to three-bet for value. Call and realize equity in "
            f"position. (My read, not a solver pull.)",
        )

    # Out of position (SB / non-IP), or in position but too weak to flat:
    # 3-bet-or-fold → fold. Green only for clear trash; a marginal fold is a read.
    return _decision(
        "fold", Confidence.GREEN if score < 30 else Confidence.YELLOW,
        "3-bet-or-fold",
        f"{h} folds versus a {opp.upper()} open from {pos.upper()} — not in the "
        f"value/bluff three-bet range and {'out of position' if pos in ('sb', 'bb') else 'not a clear flat'}, "
        f"so it's a fold here.",
    )


# ---------------------------------------------------------------------------
# vs-3BET decision (the original raiser facing a 3-bet)
# ---------------------------------------------------------------------------

def vs_3bet_decision(position: str, hand: str, threebettor: str) -> SixMaxDecision:
    """Decision facing a 3-bet after opening: 4-bet / call / fold.

    Mirrors HU button_vs_3bet_decision: value 4-bets, suited wheel-ace 4-bet
    bluffs, a call band for strong hands, fold the rest."""
    pos = _canon_pos(position)
    tb = _canon_pos(threebettor)
    h = normalize_hand(hand)
    hero_ip = _SEAT_ORDER.get(pos, 9) > _SEAT_ORDER.get(tb, -1)
    # Approximate the 3-bet size we're facing for 4-bet sizing.
    facing_3bet = round(_OPEN_SIZE_BB * (_THREE_BET_OOP_MULT if not hero_ip else _THREE_BET_IP_MULT), 1)
    fbet = round(facing_3bet * (_FOUR_BET_IP_MULT if hero_ip else _FOUR_BET_OOP_MULT), 1)

    if h in _4BET_VALUE:
        return _decision(
            "4bet", Confidence.GREEN, "4-bet value",
            f"{h} is a pure four-bet for value versus a {tb.upper()} three-bet. "
            f"Four-bet to about {fbet:g} big.",
            sizing_bb=fbet,
        )
    if h in _4BET_VALUE_MIXED:
        return _decision(
            "4bet", Confidence.YELLOW, "4-bet-or-call mix (value)",
            f"{h} is a four-bet-or-call mix versus a {tb.upper()} three-bet — "
            f"strong enough to four-bet, fine to call and play on. Leaning four-bet "
            f"to about {fbet:g} big.",
            frequency=0.5, is_mixed=True, alternative="call", alt_frequency=0.5,
            sizing_bb=fbet,
        )
    if h in _4BET_BLUFF:
        return _decision(
            "4bet", Confidence.YELLOW, "4-bet bluff (suited wheel ace)",
            f"{h} is the canonical four-bet bluff — it blocks ace-king and aces and "
            f"makes a wheel. My read leans four-bet to about {fbet:g} big, but folding "
            f"is fine too.",
            frequency=0.5, is_mixed=True, alternative="fold", alt_frequency=0.5,
            sizing_bb=fbet,
        )

    score = _score(h)
    if score >= 76:
        return _decision(
            "call", Confidence.YELLOW, "Call the 3-bet",
            f"{h} calls the {tb.upper()} three-bet — enough equity and playability "
            f"to continue{' in position' if hero_ip else ''}, not a four-bet. "
            f"(My read on the continue range, not a solver pull.)",
        )

    return _decision(
        "fold", Confidence.GREEN if score < 64 else Confidence.YELLOW,
        "Fold to the 3-bet",
        f"{h} folds to a {tb.upper()} three-bet — not enough to four-bet or call an "
        f"inflated pot. Let it go.",
    )


# ---------------------------------------------------------------------------
# Serialization + lookup orchestrator (the tool entry point)
# ---------------------------------------------------------------------------

_SOURCE = "6-max preflop engine (published ranges, SIX_MAX_NOTES.md)"


def serialize(decision: SixMaxDecision) -> dict[str, Any]:
    """SixMaxDecision -> the normalized {data, confidence, source} dict, matching
    hu_trainer._serialize_preflop key-for-key."""
    return {
        "data": {
            "action": decision.action,
            "frequency": decision.frequency,
            "is_mixed": decision.is_mixed,
            "alternative": decision.alternative,
            "alt_frequency": decision.alt_frequency,
            "sizing_bb": decision.sizing_bb,
            "principle": decision.principle,
            "explanation": decision.explanation,
        },
        "confidence": decision.confidence.value,
        "source": _SOURCE,
    }


def _decline(note: str) -> dict[str, Any]:
    # A decline carries no data + an explicit note — honest "no solver pull here"
    # (amber), never a number. Distinct from a grounded green/yellow answer.
    return {"data": None, "confidence": Confidence.AMBER.value, "source": _SOURCE, "note": note}


def _parse_action(action: str) -> tuple[str | None, str | None]:
    """'co_open_2.5' -> ('co', 'open'); 'btn_3bet_8' -> ('btn', '3bet')."""
    parts = action.lower().split("_")
    if not parts:
        return None, None
    pos = _canon_pos(parts[0]) if parts[0] in _POSITION_ALIASES else None
    kind = parts[1] if len(parts) > 1 else None
    if kind in ("raise", "rfi", "or"):
        kind = "open"
    return pos, kind


def lookup(position: str, hand: str, actions: list[str] | None = None) -> dict[str, Any]:
    """Route a 6-max preflop spot to the right decision and return the normalized
    dict. Out-of-v1-scope spots decline with data=None + note instead of guessing."""
    pos = _canon_pos(position)
    actions = [a for a in (actions or []) if a and a.strip()]

    # Validate the hero seat on EVERY path (not just RFI). A garbled position
    # must decline to amber, never fabricate a confident green/yellow line for a
    # seat that doesn't exist. _SEAT_ORDER is exactly {utg,mp,co,btn,sb,bb}.
    if pos not in _SEAT_ORDER:
        return _decline(
            f"Couldn't map hero position {position!r} to a 6-max seat. "
            "Say UTG, MP, CO, BTN, SB, or BB."
        )

    try:
        h_norm = normalize_hand(hand)  # validate early; bad input -> decline, never crash
    except ValueError as exc:
        return _decline(f"Couldn't parse hand {hand!r} ({exc}). Re-state the hand like 'A K suited'.")

    parsed = [_parse_action(a) for a in actions]
    kinds = [k for (_, k) in parsed]

    # No prior action -> RFI (the SB opens when folded to; the BB cannot RFI).
    if not actions:
        if pos == "bb":
            return _decline(
                "The big blind doesn't open first-in — it's already posted and acts "
                "last preflop. Pass the open it's facing, e.g. action_so_far=['btn_open_2.5']."
            )
        return serialize(open_decision(pos, h_norm))

    # Out-of-scope escalations: 4-bet+ wars, limped pots, multiway.
    if any(k in ("4bet", "5bet", "limp", "call") for k in kinds) and "3bet" not in kinds:
        return _decline(
            "That line is past the v1 six-max grounded set (4-bet+ pots, limped or "
            "multiway). No solver pull here — reason from the spot and flag it's a read."
        )
    if any(k in ("4bet", "5bet") for k in kinds):
        return _decline(
            "Four-bet-and-beyond pots aren't in the v1 six-max grounded set. "
            "No solver pull — give your read and flag it."
        )

    # Facing a 3-bet: hero must be the original opener.
    if "3bet" in kinds:
        threebettor = next((p for (p, k) in parsed if k == "3bet" and p), None)
        hero_opened = any(p == pos and k == "open" for (p, k) in parsed)
        if threebettor and hero_opened:
            return serialize(vs_3bet_decision(pos, h_norm, threebettor))
        return _decline(
            "Facing a three-bet without having opened (cold four-bet / squeeze spot) "
            "isn't in the v1 grounded set. Give your read and flag it."
        )

    # Facing a single open.
    if "open" in kinds:
        opener = next((p for (p, k) in parsed if k == "open" and p), None)
        if opener and opener != pos:
            return serialize(vs_open_decision(pos, h_norm, opener))
        return _decline(
            "Couldn't tell who opened from the action. Pass it like "
            "action_so_far=['co_open_2.5']."
        )

    return _decline(
        "Couldn't map that action sequence to a grounded six-max preflop spot. "
        "Supported: open, facing one open (call/3-bet), facing a 3-bet (4-bet/call/fold)."
    )


# ---------------------------------------------------------------------------
# Verification helper — combo-weighted opening % (pure=full, mixed=half).
# Used by tests to gate each range against published frequency bands.
# ---------------------------------------------------------------------------

def weighted_open_percent(position: str) -> float:
    pos = _canon_pos(position)
    pure = sum(_combos(h) for h in _OPEN_PURE[pos])
    mixed = sum(_combos(h) for h in _OPEN_MIXED[pos])
    return round((pure + 0.5 * mixed) / 1326.0 * 100.0, 1)
