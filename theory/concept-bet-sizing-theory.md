---
title: Bet-sizing theory — frequency vs sizing, polarization
source: GTO Wizard + Upswing (c-bet sizing / range morphology), cross-verified
tags: [bet-sizing, c-bet, polarization, range-advantage, nut-advantage]
---

# Bet-Sizing Theory: Small vs Large C-Bets

Here's the cleanest mental model, and it's one the serious sources agree on: **range advantage tells you how OFTEN to bet; nut advantage tells you how BIG.** GTO Wizard states this almost word-for-word — "range advantage tends to influence the frequency of bets... nut advantage, however, along with fold equity, are the primary drivers of bet sizing" ([GTO Wizard, Mechanics of C-Bet Sizing](https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/)). Burn that in. Most sizing mistakes come from conflating the two.

**Range advantage = you bet a lot of hands (high frequency).** When your range as a whole crushes theirs (think A-K-x from the preflop raiser), you can c-bet your entire range small. Upswing's "range bet" concept lives here: fire 25-33% with everything because every hand profits from the equity edge ([Upswing, Range Betting](https://upswingpoker.com/when-to-c-bet-everything/)).

**Nut advantage = you bet BIG (high sizing).** When you hold disproportionately more of the absolute nuts and your opponent can't, you're incentivized to bet large or overbet — little fear of getting raised, max value, max fold equity against their draws (GTO Wizard, above).

## The wetness parabola (this is the part people get wrong)

Sizing isn't a straight line from dry-to-wet. It's a parabola ([GTO Wizard](https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/)):

- **Dry/static (7-2-2):** small (~25-40%). Equity denial barely matters — their calling range can't improve much, so don't overpay ([Upswing, C-Bet Sizing](https://upswingpoker.com/c-bet-sizing-strategy-continuation-bet/)).
- **Wet/dynamic (K-Q-8 two-tone):** large (~66-80%). High fold-equity value; you're charging draws and protecting vulnerable value ([Upswing](https://upswingpoker.com/c-bet-sizing-strategy-continuation-bet/)).
- **VERY wet (Q-J-T monotone):** small *returns*, and frequency drops toward a ~50/50 bet-check split — because now BOTH ranges are loaded with nutted hands, so neither side has a clean nut edge to press ([GTO Wizard](https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/)).

## Polarized vs merged

The hinge is **medium-strength hands** ([GTO Wizard, Range Morphology](https://blog.gtowizard.com/range-morphology/)). A polarized range — nuts and napkins, few mediums — *wants* to be big, ideally geometric, to play for stacks. A merged range (strong + medium + weak) takes a smaller size; it's more robust and less exploitable over multiple streets. Upswing maps this to sizing directly: condensed range → 25-40%, in-between → 50-60%, polarized → 66-75% ([Upswing](https://upswingpoker.com/c-bet-sizing-strategy-continuation-bet/)).

**Board coverage** ties it together: if your range covers the strongest hands a board can make AND your opponent's can't, you have nut advantage → size up. If the board hits their calling range's nuts as hard as yours, your edge collapses → size down or check.

**Honest caveat:** these percentages are source-consensus ranges, not solver gospel. Exact frequencies shift with position, SPR, and rake. Treat the *direction* as law, the *numbers* as defaults to pressure-test in a solver.
