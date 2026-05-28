---
title: Heads-up turn play — barreling and sizing by texture
source: GTO Wizard + Upswing (turn strategy / barreling bricks), cross-verified
tags: [turn, barreling, c-bet, sizing, polarization, heads-up]
---

# Heads-Up Turn Play: Barrel or Check, and Sizing by Texture

After you c-bet the flop and get called, the turn forces a decision your flop didn't: the field has narrowed, and your line should now be *more polarized* than it was a street ago. GTO Wizard's "Principles of Turn Strategy" describes turn ranges splitting hard by hand class -- strong hands (sets, two pair) bet big, often overbet; one-pair hands mostly check for pot control; weak hands either fire a real bluff or give up. The flop's small "equity-pushing" bets largely disappear ([GTO Wizard, Principles of Turn Strategy](https://blog.gtowizard.com/principles-of-turn-strategy/)).

**Whether to barrel hinges on what the turn card did to ranges -- not your hand alone.** A second barrel works when the turn is *bad for the caller's range*. Overcards are the classic green light: an A or K turn shifts range advantage back to you (the preflop raiser holds more of those combos), so betting frequency rises. Low offsuit bricks (a 7, say) cut by texture: on a *dynamic* board where you lack the nut advantage -- a 7 on 9-8-6, say -- they push you toward checking more and smaller sizing; but on a *static, dry* board a brick usually preserves your range advantage and stays a high-frequency small-bet spot ([GTO Wizard](https://blog.gtowizard.com/principles-of-turn-strategy/); [Upswing, Barreling Bricks](https://upswingpoker.com/c-bet-turn-barreling-bricks/)).

**Sizing tracks board texture via the static/dynamic split.** On static boards (e.g., J66) most turns don't move equities, so weak hands stay weak and a small bet (~third pot) prints folds. On dynamic boards (e.g., 986, two-tone) turns complete draws and bring overcards, so when you do barrel you go bigger (half to two-thirds+) to charge equity and protect ([PokerSkill, Double Barrel](https://www.pokerskill.com/poker-glossary/double-barrel/); [GTO Wizard, C-Bet Sizing Mechanics](https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/)).

**Nut advantage is the license to overbet.** When you hold the nutted region but few medium hands, polarize large; without that nut edge, you're stuck with smaller, less polar sizes ([GTO Wizard, C-Bet Sizing](https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/)).

On range *construction*: at a 75%-pot bet, turn ranges balance near ~49% value / 51% bluff, derived from needing to barrel rivers ~70% with a ~70:30 value ratio (Janda's multi-street math via [Upswing, Barreling Bricks](https://upswingpoker.com/c-bet-turn-barreling-bricks/)). Treat that as a *range-building target*, not a "fire 49% of the time" rule. Pick bluffs that block the caller's strong hands and can improve (OESDs, flush draws, blocker gutshots); abandon backdoor misses and weak gutshots.

Position colors all of it: in position you barrel wider and value-bet thinner; out of position, tighten up and pick pot control with marginal hands ([PokerSkill, SRP](https://www.pokerskill.com/poker-glossary/single-raised-pot-srp/)).

**Honest caveat:** the cleanest solver frequencies above come from 6-max/SRP studies, not pure HU sims. HU ranges are wider, so barrel frequencies skew *higher* and overbets show up more -- the principles hold, but treat any exact percentage as directional, not gospel.
