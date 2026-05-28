---
title: Range advantage on the flop
source: General modern theory consensus (Upswing, Run It Once, GTO Wizard)
tags: [postflop, ranges, c-bet, equity]
---

# Range advantage

Range advantage is who holds more equity across their entire range on a given
board, *not* who holds more equity with the specific hand. The preflop aggressor
usually has range advantage on high-card boards because their range is weighted
toward broadway holdings. The preflop caller has range advantage on low and
middling connected boards because the aggressor's range is capped at the top.

When you have range advantage, you can bet small at high frequency. This is the
basis of the modern "small c-bet" approach: 25-33% pot, near-100% frequency on
dry high-card boards. The small sizing extracts thin value from your range as a
whole and folds out the bottom of villain's range — both wins.

When you lack range advantage (e.g. BTN on a 765 board), you check more often
and bet larger when you do. Defenders with range advantage can attack with
check-raises because their range supports it.

The mistake recreational players make: choosing sizing based on hand strength
("I have nothing, small bet; I have a hand, big bet"). That's a tell. Solver
chooses sizing based on board / range advantage, then mixes hands within each
sizing.
