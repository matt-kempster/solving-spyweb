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
