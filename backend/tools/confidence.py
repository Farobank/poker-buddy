"""Confidence tags for strategy claims.

Every numeric/factual claim the buddy makes carries a confidence level so the
voice agent can verbally signal it ("solver-verified" vs "my read, not looking
this up directly"). This is the world-class discipline rule: never assert a
GTO frequency without the source's confidence attached.

Tags borrowed from hu-poker-trainer's STRATEGY_NOTES.md verification log.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal


class Confidence(str, Enum):
    """Confidence tier for a strategy claim.

    GREEN  — direct solver lookup, multiple sources cross-verified.
    YELLOW — theory-grounded with a single named source, or solver-extrapolation.
    AMBER  — principle-based reasoning, no direct data. Surface the uncertainty.
    """

    GREEN = "green"
    YELLOW = "yellow"
    AMBER = "amber"


ConfidenceLiteral = Literal["green", "yellow", "amber"]


VOICE_PREFIX: dict[Confidence, str] = {
    Confidence.GREEN: "Solver-verified:",
    Confidence.YELLOW: "Theory-grounded, not looking it up directly:",
    Confidence.AMBER: "Just my read, no direct data:",
}


def voice_prefix(tag: Confidence | ConfidenceLiteral) -> str:
    """The natural-language prefix the agent uses when stating the claim out loud."""
    return VOICE_PREFIX[Confidence(tag)]


def is_green(tag: Confidence | ConfidenceLiteral | None) -> bool:
    return tag == Confidence.GREEN or tag == "green"
