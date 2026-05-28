---
title: Board texture categories
source: General modern theory consensus + STRATEGY_NOTES.md (hu-poker-trainer board.py)
tags: [board, texture, classification]
---

# Board texture categories

Boards cluster into a handful of texture categories that drive the same
strategy. The names below match hu-poker-trainer's classifier and modern
common usage.

- **Dry high-card** (e.g. K72r, A82r, Q72r): one high card, no draws.
  Aggressor's range advantage is biggest here. Small c-bet near-100%.

- **Broadway-heavy** (KQT, AKJ, JT9 with two broadways): wide ranges of
  big made hands and big draws. Sizings are larger, frequencies lower than
  dry high-card.

- **Mid-texture** (e.g. T74r, 974ss): neutral. Roughly balanced range
  advantage, medium frequencies, medium sizings.

- **Low-connected** (765ss, 543tt, 876r): defender's range advantage.
  Aggressor checks more, bets smaller when betting. Defender attacks with
  check-raises.

- **Mid-connected + flush draw** (T98ss, J97hh): wet. Big sizings, hand-
  specific play matters. Sets and overpairs bet for protection; draws bet
  for semi-bluff equity.

- **Monotone** (all one suit): equity-realization concerns dominate.
  Aggressor c-bets less; defender check-raises with flush + flush draws.

- **Paired** (777x, KKx, 66x): aggressor advantage due to range
  construction. Defenders rarely have trips; aggressor has more overpairs
  + slowplayed sets. Small c-bet at high frequency.

The pattern: classify the flop first, then ask "given this category, what's
the default frequency + sizing?" Adjust for hand strength only as a
secondary input.
