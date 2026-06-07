from pathlib import Path

from spyweb.benchmark import (
    STRATEGIES,
    Matchup,
    load_assets,
    run_matrix,
    simulate_campaign,
)
from spyweb.core.model import Faction


def test_benchmark_assets_use_sampled_universe_boards(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 500)
    knowledge = assets.knowledge_of(Faction.BIRD)

    assert knowledge.universe.board_count == 500
    assert knowledge.encoding.rules.spies[0].faction is Faction.BIRD


def test_simulates_ai_campaign_on_small_universe(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 2_000)
    metrics = simulate_campaign(
        assets,
        matchup=Matchup(STRATEGIES["frugal"], STRATEGIES["frugal"]),
        seed=7,
        max_rounds=20,
        max_actions_per_round=80,
    )

    assert metrics.winner in (0, 1)
    assert metrics.starting_player == 0
    assert metrics.rounds >= 1
    assert sum(metrics.actions) > 0
    assert sum(metrics.accusations) > 0


def test_strategy_matrix_aggregates_results(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 1_000)
    results = run_matrix(
        assets,
        [STRATEGIES["frugal"], STRATEGIES["defensive"]],
        campaigns=1,
        seed=3,
    )

    assert len(results) == 4
    assert all(result.campaigns == 1 for result in results)
