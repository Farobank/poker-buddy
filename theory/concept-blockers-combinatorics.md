---
title: Blockers and combinatorics — counting combos, picking bluffs
source: GTO Wizard + Upswing + SplitSuit (combinatorics / blockers), cross-verified
tags: [blockers, combinatorics, bluff-selection, bluff-catching, card-removal]
---

# Blockers and Combinatorics

Combinatorics is just counting how many ways a hand can exist. Memorize the three numbers and you'll never be lost: **every unpaired hand has 16 combos (4 suited + 12 offsuit), every pocket pair has 6.** There are **1,326 total preflop combos** — 78 pairs, 312 suited, 936 offsuit ([GTO Wizard](https://blog.gtowizard.com/a-beginners-guide-to-poker-combinatorics/); [Upswing](https://upswingpoker.com/how-the-pros-take-advantage-of-hand-combinations/)).

Now subtract for known cards. With *a* available cards of a rank, **pairs = a×(a−1)/2** and **unpaired = a×b**. So if one ace is on board, AA drops from 6 to 3 [(3×2)/2]. With an ace AND king out, AK falls from 16 to 9 [3×3] ([GTO Wizard](https://blog.gtowizard.com/a-beginners-guide-to-poker-combinatorics/)). That's the whole engine — count value combos vs. bluff combos in your opponent's range, compare to your pot odds, and you have a math-backed call or fold.

**Bluff selection — block value, unblock folds.** A great bluff does two jobs at once: it holds cards that *block* the hands that would call/raise, and *avoids* cards that block the hands that would fold. As GTO Wizard puts it, "a good bluff should simultaneously block very strong hands and unblock the hands that we want to fold out" ([Blockers & Unblockers](https://blog.gtowizard.com/blockers-unblockers-the-secret-to-picking-great-bluffs/)). Classic example: on a board where the nuts is a straight, a hand like 8♠4♠ blocks the straight while leaving villain's busted Broadway combos (the folds) fully intact. Preflop, A5s is the canonical raise/bluff — and the first reason is equity, not blockers: it makes the nut flush and wheel straights, so it has real playability when it gets called. On top of that the ace blocks villain's strong ace-x (A-A, A-K, A-Q), and the low card avoids blocking the weak hands you want to fold out.

**Bluff-catching — flip the logic.** When you're deciding whether to call down, you want to **block value and unblock bluffs.** Blocking villain's bluffs actively *hurts* your call, because it lowers the chance they're bluffing right now ([Understanding Blockers](https://blog.gtowizard.com/understanding-blockers-in-poker/)). Holding a card that wrecks his missed-draw combos? That's a reason to fold a marginal bluff-catcher, not call it.

**The big caveat — don't worship blockers.** GTO Wizard's call-decision hierarchy is explicit and in order: (1) Do I beat bluffs? (2) Is villain over- or under-bluffing? (3) Do my blockers matter? Reads come first: "If you suspect your opponent is over or under-bluffing, this supersedes blockers in nearly every spot" ([Understanding Blockers](https://blog.gtowizard.com/understanding-blockers-in-poker/)). In their T♠9♠ example, just 1% more bluffing flips a blocker-fold into a pure call. Blockers are the tiebreaker on close spots — they bite hardest preflop and on the river, and matter less on the flop/turn where your hand's improvability dominates ([Blockers & Unblockers](https://blog.gtowizard.com/blockers-unblockers-the-secret-to-picking-great-bluffs/)). Count first, read first, break ties with blockers.
