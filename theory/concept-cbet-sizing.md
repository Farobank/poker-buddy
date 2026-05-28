---
title: C-bet sizing is a property of the board, not the hand
source: General modern theory consensus; mirrors STRATEGY_NOTES.md
tags: [postflop, c-bet, sizing]
---

# C-bet sizing

Sizing is determined by the board, not the hand. Every hand you bet on a given
flop goes at the same size; what changes is the *frequency* of betting.

Rough heuristics for the preflop aggressor heads-up:

- Dry high-card boards (K72r, A82r): bet 25-33% pot at ~80-100% frequency
- Broadway-heavy boards (KQT, JT9): bet 33-50% pot at ~60-75% frequency
- Wet / low-connected boards (876ss, T98r): bet 50-75% pot at ~50-70% frequency
- Paired boards (777x, 66x): bet small ~30% pot at ~70-85% (paired boards favor
  preflop aggressor due to range-construction asymmetry)
- Monotone (all one suit): bet 33-50% at ~40-55% frequency; equity-realization
  concerns dominate
- 4-bet pots: bet near-pot at ~85-100% (range condensed and well ahead)

Inside a single sizing tier, mix hands: some pure bets (sets, top pair, gutshots,
backdoor flush draws), some pure checks (medium pairs that hate getting raised,
weak draws on certain runouts), and mixed-frequency hands.

The voice-friendly framing: "On K-seven-two rainbow, BTN's c-betting around
ninety percent of their range at about a third pot. Almost every hand bets at
the same sizing — different hands just bet at different frequencies."
