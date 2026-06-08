# Human Component Strategy

This strategy formalizes the reasoning captured in
[`2026-06-08-human-bird-vs-component-sea-round-1.md`](../game-traces/2026-06-08-human-bird-vs-component-sea-round-1.md).
It is intentionally separate from the older `component` policy so the two can
be benchmarked against each other.

## State

The policy derives these facts from the observation log:

- questions already asked;
- how many Nothing answers each spy has produced;
- connected components created by spy-to-spy answers;
- components anchored by landmark answers;
- the current belief over full boards, ringleaders, and hideouts.

## Phases

### Explore

Used before a useful component exists.

1. Prefer a spy with several remaining legal questions.
2. Prefer directions likely to hit a landmark, then another spy.
3. Move away from a spy after it produces Nothing instead of overcommitting to
   a possible ringleader or edge case.

### Build

Used once a component or landmark anchor exists.

1. Ask from the largest useful component.
2. Prefer answers that merge another spy or component into it.
3. Prefer questions that narrow the hideout and fit the remaining board shape.
4. Avoid repeated and adversarially uninformative questions.

### Leader Hunt

Used once the hideout is fixed.

1. Minimize the worst-case and expected number of remaining ringleaders.
2. Prefer asking suspicious spies that still have high ringleader probability.
3. Continue until the ringleader/hideout pair is unique, then accuse.

## Tuning Contract

Changes should be evaluated on both:

- behavioral scenarios, such as abandoning an early Nothing source and
  expanding `Raven -> Eagle` via Raven's other direction;
- campaign win rate against the existing minimax, component, hybrid, and simple
  baselines.

The strategy is selected as `human` in the web UI and benchmark CLI.
