# Spy Web solver

A strictly typed Python/NumPy foundation for solving and auditing Spy Web.

Requested future work and larger design items are tracked in
[ROADMAP.md](ROADMAP.md).

The project separates:

- `spyweb.core`: authoritative game vocabulary and question resolution
- `spyweb.solver`: compact NumPy board universe, filtering, and scoring
- `spyweb.cli`: interactive physical-game solving assistant

The bundled bird and sea card data comes from the supplied transcription.
An unavailable sense is represented explicitly as an empty direction list and
is never offered as a legal question.

## Setup

```bash
uv sync
uv run spyweb
```

Play a vanilla two-player hot-seat game:

```bash
uv run spyweb-play
```

Or run the small local browser UI:

```bash
uv run spyweb-web
# open http://127.0.0.1:8000
```

The browser UI is an additional hot-seat interface; it does not replace the
TUI. It shows the selected player's private board, card directions, actions,
knowledge bases, and game log. Its drag-and-drop deduction board is stored only
in browser `localStorage` and does not change authoritative game state.
Before each web round, players can drag their visible spies and hideout into a
private layout and lock it before play begins.

Play against the same server-side solver AI used by the TUI:

```bash
uv run spyweb-web --ai
```

The first AI launch builds the exact Bird-board knowledge cache. No solver code
or private AI state runs in or is sent to the browser.
For AI games, Sea chooses its own private layout server-side with a randomized
defensive heuristic, so it should not repeat the same permutation every round.

The browser also visualizes each player's event-derived deduction graph:
asked/unasked senses, spy-to-spy edges, landmark anchors, and nothing answers.
AI deductions and its textual knowledge base remain hidden until the
`Show AI knowledge` control is enabled.

Optional local card art can be placed under the git-ignored
`spyweb/web_static/local_art/` directory. Copy
[`docs/local-art-manifest.example.json`](docs/local-art-manifest.example.json)
to `spyweb/web_static/local_art/manifest.json`, add your locally sliced PNGs,
and update the paths. This keeps user-provided scans out of the repository.
For 3x3 Bird and Sea card-sheet scans, `ffmpeg` can slice and configure them:

```bash
uv run spyweb-slice-art --bird path/to/birds.jpg --sea path/to/sea.jpg
```

The emulator generates both private boards, shows the current player's board,
lists legal questions by number, resolves answers automatically, supports
accusations, and clears the terminal before passing turns. Raven points north
and south; Urchin points east and west. The responding player chooses which
truthful answer to reveal first, and the asker may pay `$100,000` for the other
answer. After any action, the active player may transfer `$100,000` to the
opponent to take one additional action that turn. The Raven/Urchin
second-direction bribe is independent and does not consume that extra action.

The emulator plays the official multi-round campaign. Each player starts with
`$100,000`; correct accusations earn the captured leader's printed bounty; the
loser starts the next round; and both players collect a `$100,000` salary before
that round. The campaign ends after a round when a player has at least
`$1,000,000`. If both qualify, higher cash wins; a tie triggers another round.

Starting money is configurable for testing:

```bash
uv run spyweb-play --starting-money 500000
```

Play Bird against the solver-driven Sea AI:

```bash
uv run spyweb-play --ai
```

The first AI game builds and caches an exact `3,265,920`-board Bird knowledge
base at `.cache/play-ai-bird.npz`. Later games load that cache. During play,
the emulator displays the opponent faction's look/hear/point directions and
both players' accumulated observation knowledge bases.

The AI scores every legal question at the root using adversarial minimax. It
searches one question ahead above `250,000` possible boards, two questions
ahead down to `25,000`, and three questions ahead below that, with the five
best immediate questions considered at recursive nodes. Payments are
campaign-aware and conservative: the AI only pays when the resulting immediate
accusation guarantees a campaign-critical outcome.

When playing against the AI in the web UI, use the header's **AI strategy**
selector to switch between the bounded minimax policy, the original
component-building policy, a human-style component policy, and human-prior
minimax.

Run a repeatable AI-vs-AI strategy and faction benchmark:

```bash
uv run spyweb-benchmark --campaigns 100
```

The benchmark runs every selected Bird strategy against every selected Sea
strategy, reports campaign win rates with 95% confidence intervals, and uses
the same rules engine, beliefs, questions, accusations, payments, extra
actions, bounties, and `$1,000,000` campaign target as interactive play.
The benchmark uses all `3,265,920` legal boards per faction by default. The
ringleader is selected uniformly first; random setup samples a legal layout
conditional on that ringleader, while defensive setup samples and scores
layouts without choosing the leader. For throughput, each AI evaluates a
1,000-board particle belief that always includes the true board; this still
draws true setups from the full universe. Use `--belief-boards 0` for exact
full-universe policy evaluation, `--boards 50000` to restrict the true-board
universe during development, `--no-cache` to rebuild solver universes in
memory, and `--json-out results.json` for machine-readable results. Policy
search defaults to depth 1 for fast sweeps; use `--max-depth 2` or
`--max-depth 3` for slower lookahead experiments.

The benchmark includes a `component` strategy modeled after human constraint
solving. It prioritizes questions that reduce possible ringleaders, grow or
anchor known connected components, and are likely to produce a spy or other
non-Nothing answer. Its answer probabilities are conditioned on the current
belief, so its preferred directions adapt as the possible board shapes narrow.
The separate `human` strategy follows an explicit explore/build/leader-hunt
state machine: it starts with spies that have several useful directions, moves
away from early Nothing answers, expands its best known component, and switches
to ruling out ringleaders once the hideout is fixed. Its behavioral contract is
documented in [`docs/strategies/human-component.md`](docs/strategies/human-component.md).
The `prior` strategy uses that human policy to contribute candidates to a
diverse action shortlist at every recursive node, then lets bounded minimax
choose among them.
It also includes an experimental `hybrid` strategy that uses component scores
to shortlist candidate questions, applies bounded minimax inside that shortlist,
and switches to an exact solve-to-accusation search in small endgames.
The deliberately simple `nonnull` baseline merely asks the unasked question
most likely to produce anything other than Nothing.

Use a representative development sample:

```bash
uv run spyweb --boards 50000
uv run spyweb --faction sea --boards 50000
```

Export either bundled faction to an editable, versioned transcription file:

```bash
uv run spyweb --export-rules rules.json
uv run spyweb --faction sea --export-rules sea-rules.json
uv run spyweb --rules rules.json --boards 50000
```

Persist and reuse a complete-universe cache:

```bash
uv run spyweb --boards 3265920 --cache .cache/spyweb-full.npz
```

Persist an auditable JSON trace while playing:

```bash
uv run spyweb --boards 50000 --trace-out game.json
```

Resume by replaying a saved trace:

```bash
uv run spyweb --boards 50000 --trace-in game.json --trace-out game.json
```

Universe caches and audit traces include a rules fingerprint. The solver rejects
stale, differently sized, or incompatible data instead of silently mixing card
transcriptions.

Enable bounded adversarial lookahead once the belief is small enough:

```bash
uv run spyweb --lookahead-depth 2 --lookahead-max-boards 10000
```

Lookahead treats the opponent's first dual-direction answer adversarially. Paid
second-answer decisions are currently shown separately rather than folded into
the recursive policy.

Within the assistant:

- `a`: record an ordinary or first dual-direction answer
- `s`: record a paid second direction after its first answer
- `x`: record a correct or incorrect accusation
- `p`: inspect the recommended question's answer partitions
- `c`: inspect remaining ringleader/hideout candidate counts
- `t`: inspect the audit trace
- `u`: undo the last event

## Verification

```bash
uv run mypy spyweb tests
uv run ruff check .
uv run pytest
```
