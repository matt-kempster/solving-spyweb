# Spy Web Roadmap

This file records requested work that is not yet complete. Keep the TUI and web
UI backed by the same authoritative rules and AI modules.

## Setup And Defensive Layouts

- [x] Add a setup phase to the web UI. The player's ringleader remains randomly
  assigned, while the player drags the hideout and eight visible spies onto the
  board and locks the layout before play begins.
- [x] Make the AI choose its hideout and permutation after receiving its random
  ringleader.
- [x] Do not make the AI's defensive setup deterministic. Score layouts, retain a
  pool of strong and strategically distinct candidates, and sample from a
  mixed policy so repeated games do not reveal one reusable layout.
- Add an auditable setup event without revealing the
  opponent's private layout.

## Deduction UI

- [x] Support a 3x3 scratch-space for groups whose relative arrangement is
  known but whose absolute board position is not. Browser-only bins are
  implemented; future work should support moving a whole component and drawing
  explicit relative-position edges.
- [x] Visualize event-derived relative-position edges, landmark anchors,
  nothing answers, and which senses each player has or has not asked about.
- Visualize belief-derived components and possible ringleaders/hideouts.
- Keep AI knowledge hidden by default so the player cannot bias decisions based
  on how close the AI is. The web UI now has an explicit show/hide control.

## Stronger AI

- [x] Build a repeatable evaluation harness that plays policies against each other
  across many random boards and campaign states. Track round win rate,
  campaign win rate, solve actions, cash transfers, and setup diversity.
- [x] Run a configurable initial AI-vs-AI strategy matrix spanning asking, accusation,
  payment, extra-action, and defensive-layout policies. Report confidence
  intervals, head-to-head grids, Bird-versus-Sea faction advantage, and results
  with factions swapped so strategy strength is separated from faction strength.
- [x] Add high-throughput benchmark mode. True setups are sampled from all legal
  boards while AI decisions use configurable particle beliefs; 1,000 particles
  runs roughly 14 campaigns/second on the development machine. Exact beliefs
  remain available with `--belief-boards 0`.
- [x] Add a component-building strategy that prioritizes ringleader elimination,
  connected-component growth and anchoring, likely spy answers, and
  belief-conditioned non-Nothing directions.
- [x] Add an experimental hybrid strategy that blends component-guided candidate
  ordering with bounded minimax and exact small-pair endgame search.
- Continue optimizing exact-universe policy evaluation. Reusable policy
  decisions and faster partition scoring reduced a depth-1 exact campaign to
  roughly 45 seconds, but large exact matrices are not yet routine.
- Replace the current question-only bounded minimax objective with a race-aware
  policy that models both players' progress, bounties, campaign cash, optional
  payments, accusations, and turn order.
- Track or estimate the human player's belief state from the questions they ask
  and use it when valuing extra actions and Raven/Urchin payments.
- Add stronger endgame search and a defensive-layout optimizer. Use exhaustive
  scoring where practical and stochastic search or candidate refinement where
  full policy simulation is too expensive.
- Preserve auditable recommendations and traces even when policies become more
  sophisticated.

## Visual Presentation

- Give the web UI a stronger period board-game presentation while preserving
  clear card directions and accessibility.
- Use the following BoardGameGeek scans as visual references:
  - https://cf.geekdo-images.com/odaVXXDOooc01Yzb8Yq4IA__imagepage/img/FuDbnHvPf4WKCcGidM39iPp7c84=/fit-in/900x600/filters:no_upscale():strip_icc()/pic283090.jpg
  - https://cf.geekdo-images.com/VGzo42xNf1JsHaeGWjjAhA__imagepage/img/3yzPbvWbJ5E6L827m0J1oMzXhUU=/fit-in/900x600/filters:no_upscale():strip_icc()/pic283092.jpg
  - https://cf.geekdo-images.com/N1RekXvTFkev7UIZtFgZ-g__imagepage/img/Vd3LzhFhz7LqYKRSHBXTccdPDP0=/fit-in/900x600/filters:no_upscale():strip_icc()/pic855282.jpg
- Confirm permission or licensing before bundling scans or cropped artwork in
  the repository. Until then, derive styling, layout, colors, and original
  assets without copying the scans.
