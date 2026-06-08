from pathlib import Path
from random import Random

from spyweb.benchmark import (
    STRATEGIES,
    Matchup,
    PolicyCache,
    TrackedKnowledge,
    _choose_action,
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


def test_sampled_knowledge_has_requested_size_and_true_board(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 2_000)
    knowledge = assets.sampled_knowledge_of(
        Faction.BIRD,
        true_board=1_337,
        boards=100,
        random=Random(4),
    )

    assert knowledge.belief.size == 100
    assert 1_337 in knowledge.belief
    assert len(set(map(int, knowledge.belief))) == 100


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


def test_policy_action_cache_reuses_identical_belief(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 1_000)
    knowledge = TrackedKnowledge(assets.knowledge_of(Faction.BIRD))
    cache: PolicyCache = {}

    first = _choose_action(knowledge, STRATEGIES["frugal"], cache)
    size_after_first = len(cache)
    second = _choose_action(knowledge, STRATEGIES["frugal"], cache)

    assert second == first
    assert size_after_first == 1
    assert len(cache) == size_after_first


def test_hybrid_strategy_selects_an_action(tmp_path: Path) -> None:
    assets = load_assets(tmp_path, 1_000)
    knowledge = TrackedKnowledge(assets.knowledge_of(Faction.BIRD))

    action = _choose_action(knowledge, STRATEGIES["hybrid"], {})

    assert action is not None
