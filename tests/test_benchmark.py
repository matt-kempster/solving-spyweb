from pathlib import Path
from random import Random

from spyweb.benchmark import (
    STRATEGIES,
    Matchup,
    _choose_board,
    load_assets,
    run_matrix,
    simulate_campaign,
)
from spyweb.core.model import Faction, SpyId


def test_benchmark_assets_use_sampled_universe_boards(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 500)
    knowledge = assets.knowledge_of(Faction.BIRD)

    assert knowledge.universe.board_count == 500
    assert knowledge.encoding.rules.spies[0].faction is Faction.BIRD


def test_benchmark_can_build_without_writing_cache(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 500, use_cache=False)

    assert assets.bird.board_count == 500
    assert not tuple(tmp_path.iterdir())


def test_setup_policy_preserves_randomly_selected_ringleader(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 2_000)

    for name in ("frugal", "defensive"):
        expected = SpyId(Random(3).randrange(9))
        board = _choose_board(
            assets.bird,
            assets.bird_encoding,
            STRATEGIES[name],
            Random(3),
        )
        assert board.ringleader == expected


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
