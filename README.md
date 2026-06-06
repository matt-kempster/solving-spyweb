# Spy Web solver

Strictly typed Spy Web rules, auditable event replay, compact solver encoding,
and an initial terminal interface.

## Commands

```sh
pnpm install
pnpm check
pnpm test
pnpm tui
```

The card directions in `src/core/catalog.ts` are deliberately marked as a
fixture. Replace them with a verified transcription before treating solver
recommendations as authoritative.

## Structure

- `src/core`: game vocabulary, board validation, question resolution, events
- `src/solver`: compact board universe, belief filtering, action scoring
- `src/app`: human-facing terminal interface
