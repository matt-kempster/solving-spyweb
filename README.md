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

The first run creates a cached board universe. Use a smaller development sample:

```bash
uv run spyweb --boards 50000
```

## Verification

```bash
uv run mypy spyweb tests
uv run ruff check .
uv run pytest
```
