# Spy Web solver

A strictly typed Python/NumPy foundation for solving and auditing Spy Web.

The project separates:

- `spyweb.core`: authoritative game vocabulary and question resolution
- `spyweb.solver`: compact NumPy board universe, filtering, and scoring
- `spyweb.cli`: interactive physical-game solving assistant

The bundled card directions are explicitly a development fixture. They must be
replaced with a verified transcription before recommendations are authoritative.

## Setup

```bash
uv sync
uv run spyweb
```

Use a representative development sample:

```bash
uv run spyweb --boards 50000
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

Universe caches include a rules fingerprint and board count. The solver rejects
stale or differently sized caches instead of silently using incompatible data.

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
