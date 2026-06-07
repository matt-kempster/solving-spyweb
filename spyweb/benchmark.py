from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from math import sqrt
from pathlib import Path
from random import Random

import numpy as np

from spyweb.ai import (
    AiKnowledge,
    accusation_candidate,
    ai_search_depth,
    observe_accusation,
    observe_first,
    observe_second,
)
from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import (
    ACTION_COST,
    ROUND_SALARY,
    Accusation,
    AskedQuestion,
    BoughtSecondAnswer,
    GameState,
    PlayerState,
    TurnPhase,
    accuse,
    ask_question,
    buy_extra_action,
    buy_second_answer,
    campaign_winner,
    decline_second_answer,
    end_turn,
)
from spyweb.core.model import Answer, Board, Faction, Question, Rules
from spyweb.core.rules import answer_question, rules_fingerprint
from spyweb.solver.belief import (
    PairCandidate,
    filter_first_answer,
    pair_candidates,
    pair_count,
    score_dual_payment,
)
from spyweb.solver.encoding import Encoding
from spyweb.solver.policy import recommend_questions
from spyweb.solver.universe import Universe, build_universe, universe_board_count


class SearchPolicy(StrEnum):
    GREEDY = "greedy"
    ADAPTIVE = "adaptive"


class SpendPolicy(StrEnum):
    NEVER = "never"
    TEMPO = "tempo"


class SetupPolicy(StrEnum):
    RANDOM = "random"
    DEFENSIVE = "defensive"


@dataclass(frozen=True)
class Strategy:
    name: str
    search: SearchPolicy
    spend: SpendPolicy
    setup: SetupPolicy
    defensive_samples: int = 128
    max_depth: int = 3


STRATEGIES: dict[str, Strategy] = {
    "frugal": Strategy("frugal", SearchPolicy.GREEDY, SpendPolicy.NEVER, SetupPolicy.RANDOM),
    "defensive": Strategy(
        "defensive", SearchPolicy.GREEDY, SpendPolicy.NEVER, SetupPolicy.DEFENSIVE
    ),
    "current": Strategy(
        "current", SearchPolicy.ADAPTIVE, SpendPolicy.NEVER, SetupPolicy.DEFENSIVE
    ),
    "tempo": Strategy("tempo", SearchPolicy.ADAPTIVE, SpendPolicy.TEMPO, SetupPolicy.DEFENSIVE),
}


@dataclass(frozen=True)
class Matchup:
    bird: Strategy
    sea: Strategy


@dataclass
class CampaignMetrics:
    winner: int
    starting_player: int
    rounds: int
    actions: list[int]
    questions: list[int]
    accusations: list[int]
    wrong_accusations: list[int]
    second_answers: list[int]
    extra_actions: list[int]
    final_money: list[int]


@dataclass
class Aggregate:
    bird_strategy: str
    sea_strategy: str
    campaigns: int = 0
    bird_wins: int = 0
    bird_starts: int = 0
    bird_wins_when_starting: int = 0
    sea_wins_when_starting: int = 0
    rounds: int = 0
    bird_actions: int = 0
    sea_actions: int = 0
    bird_wrong_accusations: int = 0
    sea_wrong_accusations: int = 0
    bird_spend_actions: int = 0
    sea_spend_actions: int = 0

    def add(self, metrics: CampaignMetrics) -> None:
        self.campaigns += 1
        self.bird_wins += metrics.winner == 0
        self.bird_starts += metrics.starting_player == 0
        self.bird_wins_when_starting += metrics.starting_player == 0 and metrics.winner == 0
        self.sea_wins_when_starting += metrics.starting_player == 1 and metrics.winner == 1
        self.rounds += metrics.rounds
        self.bird_actions += metrics.actions[0]
        self.sea_actions += metrics.actions[1]
        self.bird_wrong_accusations += metrics.wrong_accusations[0]
        self.sea_wrong_accusations += metrics.wrong_accusations[1]
        self.bird_spend_actions += metrics.second_answers[0] + metrics.extra_actions[0]
        self.sea_spend_actions += metrics.second_answers[1] + metrics.extra_actions[1]

    @property
    def bird_win_rate(self) -> float:
        return self.bird_wins / self.campaigns

    @property
    def bird_win_ci95(self) -> float:
        p = self.bird_win_rate
        return 1.96 * sqrt(p * (1 - p) / self.campaigns)


@dataclass(frozen=True)
class BenchmarkAssets:
    bird: Universe
    sea: Universe
    bird_encoding: Encoding
    sea_encoding: Encoding

    def knowledge_of(self, faction: Faction) -> AiKnowledge:
        universe, encoding = (
            (self.bird, self.bird_encoding)
            if faction is Faction.BIRD
            else (self.sea, self.sea_encoding)
        )
        return AiKnowledge(
            universe,
            encoding,
            np.arange(universe.board_count, dtype=np.uint32),
        )


def _layout_score(universe: Universe, encoding: Encoding, board_id: int) -> tuple[int, int]:
    answers = universe.answer0[:, board_id]
    nothing = int(np.count_nonzero(answers == encoding.nothing))
    distinct = int(np.unique(answers).size)
    return nothing, -distinct


def _choose_board(
    universe: Universe, encoding: Encoding, strategy: Strategy, random: Random
) -> Board:
    if strategy.setup is SetupPolicy.RANDOM:
        return universe.board(random.randrange(universe.board_count))
    sample_count = min(strategy.defensive_samples, universe.board_count)
    candidates = [random.randrange(universe.board_count) for _ in range(sample_count)]
    best_score = max(_layout_score(universe, encoding, board_id) for board_id in candidates)
    pool = [
        board_id
        for board_id in candidates
        if _layout_score(universe, encoding, board_id) == best_score
    ]
    return universe.board(random.choice(pool))


def _choose_action(knowledge: AiKnowledge, strategy: Strategy) -> PairCandidate | Question:
    candidates = pair_candidates(knowledge.universe, knowledge.belief)
    if len(candidates) == 1:
        return candidates[0]
    depth = (
        ai_search_depth(int(knowledge.belief.size))
        if strategy.search is SearchPolicy.ADAPTIVE
        else 1
    )
    depth = min(depth, strategy.max_depth)
    recommendation = recommend_questions(
        knowledge.universe,
        knowledge.belief,
        depth=depth,
        max_lookahead_boards=int(knowledge.belief.size),
        branching_limit=5,
    )
    if recommendation.best.immediate.worst_pairs >= len(candidates):
        return max(candidates, key=lambda candidate: candidate.boards)
    return knowledge.encoding.decode_question(recommendation.best.immediate.question)


def _adversarial_first_index(
    knowledge: AiKnowledge, question: Question, answers: tuple[Answer, ...]
) -> int:
    qid = knowledge.encoding.question_id(question)
    scores = []
    for index, answer in enumerate(answers):
        belief = filter_first_answer(
            knowledge.universe, knowledge.belief, qid, knowledge.encoding.answer_code(answer)
        )
        scores.append((pair_count(knowledge.universe, belief), int(belief.size), index))
    return max(scores)[2]


def _should_buy_second(knowledge: AiKnowledge, question: Question, first: Answer) -> bool:
    qid = knowledge.encoding.question_id(question)
    first_code = knowledge.encoding.answer_code(first)
    option = next(
        item for item in score_dual_payment(knowledge.universe, knowledge.belief, qid)
        if item.first == first_code
    )
    return (option.paid_worst_pairs, option.paid_worst_boards) < (
        option.no_pay_pairs,
        option.no_pay_boards,
    )


def _new_round(
    assets: BenchmarkAssets,
    strategies: tuple[Strategy, Strategy],
    random: Random,
    money: tuple[int, int],
    turn: int,
) -> GameState:
    return GameState(
        (
            PlayerState(
                strategies[0].name,
                BIRD_RULES,
                _choose_board(assets.bird, assets.bird_encoding, strategies[0], random),
                money[0],
            ),
            PlayerState(
                strategies[1].name,
                SEA_RULES,
                _choose_board(assets.sea, assets.sea_encoding, strategies[1], random),
                money[1],
            ),
        ),
        turn=turn,
    )


def simulate_campaign(
    assets: BenchmarkAssets,
    matchup: Matchup,
    *,
    seed: int,
    starting_player: int = 0,
    max_rounds: int = 100,
    max_actions_per_round: int = 1_000,
) -> CampaignMetrics:
    random = Random(seed)
    strategies = (matchup.bird, matchup.sea)
    knowledge = [assets.knowledge_of(Faction.SEA), assets.knowledge_of(Faction.BIRD)]
    state = _new_round(assets, strategies, random, (100_000, 100_000), starting_player)
    actions = [0, 0]
    questions = [0, 0]
    accusations = [0, 0]
    wrong_accusations = [0, 0]
    second_answers = [0, 0]
    extra_actions = [0, 0]

    for round_number in range(1, max_rounds + 1):
        round_actions = 0
        while state.winner is None:
            actor = state.turn
            strategy = strategies[actor]
            if round_actions >= max_actions_per_round:
                remaining = pair_count(knowledge[state.turn].universe, knowledge[state.turn].belief)
                raise RuntimeError(
                    f"Round exceeded {max_actions_per_round} actions; "
                    f"{state.actor.name} still has {remaining} target pairs"
                )
            if state.phase is TurnPhase.ACTION:
                action = _choose_action(knowledge[actor], strategy)
                actions[actor] += 1
                round_actions += 1
                if isinstance(action, PairCandidate):
                    state = accuse(
                        state,
                        state.opponent.rules.spies[action.ringleader].id,
                        state.opponent.rules.cities[action.hideout].id,
                    )
                    event = state.history[-1]
                    assert isinstance(event, Accusation)
                    accusations[actor] += 1
                    wrong_accusations[actor] += not event.correct
                    knowledge[actor] = observe_accusation(
                        knowledge[actor], event.ringleader, event.hideout, correct=event.correct
                    )
                else:
                    answers = answer_question(state.opponent.rules, state.opponent.board, action)
                    first_index = _adversarial_first_index(knowledge[actor], action, answers)
                    state = ask_question(state, action, first_answer_index=first_index)
                    event = state.history[-1]
                    assert isinstance(event, AskedQuestion)
                    questions[actor] += 1
                    knowledge[actor] = observe_first(knowledge[actor], action, event.answer)
                continue
            if state.phase is TurnPhase.DUAL_SECOND_ANSWER:
                pending = state.pending_second
                event = state.history[-1]
                assert pending is not None and isinstance(event, AskedQuestion)
                buy = (
                    strategy.spend is SpendPolicy.TEMPO
                    and state.actor.money >= ACTION_COST
                    and _should_buy_second(knowledge[actor], pending.question, event.answer)
                )
                if not buy:
                    state = decline_second_answer(state)
                    continue
                state = buy_second_answer(state)
                second = state.history[-1]
                assert isinstance(second, BoughtSecondAnswer)
                second_answers[actor] += 1
                knowledge[actor] = observe_second(
                    knowledge[actor], pending.question, event.answer, second.answer
                )
                continue
            assert state.phase is TurnPhase.POST_ACTION
            can_convert = accusation_candidate(knowledge[actor]) is not None
            buy_extra = (
                strategy.spend is SpendPolicy.TEMPO
                and can_convert
                and not state.extra_action_bought
                and state.actor.money >= ACTION_COST
            )
            if buy_extra and state.winner is None:
                state = buy_extra_action(state)
                extra_actions[actor] += 1
            elif state.winner is None:
                state = end_turn(state)

        winner = campaign_winner(state)
        if winner is not None:
            return CampaignMetrics(
                winner,
                starting_player,
                round_number,
                actions,
                questions,
                accusations,
                wrong_accusations,
                second_answers,
                extra_actions,
                [player.money for player in state.players],
            )
        loser = 1 - state.winner
        money = (
            state.players[0].money + ROUND_SALARY,
            state.players[1].money + ROUND_SALARY,
        )
        knowledge = [assets.knowledge_of(Faction.SEA), assets.knowledge_of(Faction.BIRD)]
        state = _new_round(assets, strategies, random, money, loser)
    raise RuntimeError("Campaign exceeded round limit")


def run_matrix(
    assets: BenchmarkAssets,
    strategies: Sequence[Strategy],
    *,
    campaigns: int,
    seed: int,
    progress: bool = False,
) -> tuple[Aggregate, ...]:
    results: list[Aggregate] = []
    for bird in strategies:
        for sea in strategies:
            aggregate = Aggregate(bird.name, sea.name)
            if progress:
                print(f"Running {bird.name} Bird vs {sea.name} Sea...")
            for campaign in range(campaigns):
                aggregate.add(
                    simulate_campaign(
                        assets,
                        Matchup(bird, sea),
                        seed=seed + campaign + len(results) * campaigns,
                        starting_player=campaign % 2,
                    )
                )
            results.append(aggregate)
    return tuple(results)


def _with_max_depth(strategy: Strategy, max_depth: int | None) -> Strategy:
    return strategy if max_depth is None else replace(strategy, max_depth=max_depth)


def _load_universe(rules: Rules, cache: Path, boards: int) -> tuple[Universe, Encoding]:
    encoding = Encoding(rules)
    expected = universe_board_count(rules, boards)
    if cache.exists():
        try:
            return (
                Universe.load(
                    cache,
                    expected_rules_fingerprint=rules_fingerprint(rules),
                    expected_board_count=expected,
                ),
                encoding,
            )
        except ValueError:
            pass
    universe = build_universe(rules, encoding, limit=boards)
    universe.save(cache)
    return universe, encoding


def load_assets(cache_dir: Path, boards: int) -> BenchmarkAssets:
    bird, bird_encoding = _load_universe(BIRD_RULES, cache_dir / f"bird-{boards}.npz", boards)
    sea, sea_encoding = _load_universe(SEA_RULES, cache_dir / f"sea-{boards}.npz", boards)
    return BenchmarkAssets(bird, sea, bird_encoding, sea_encoding)


def _print_results(results: Sequence[Aggregate]) -> None:
    print("\nBird strategy      Sea strategy       Bird wins (95% CI)  Avg rounds  Actions B/S")
    for result in results:
        print(
            f"{result.bird_strategy:<18} {result.sea_strategy:<18} "
            f"{result.bird_win_rate:>6.1%} +/- {result.bird_win_ci95:>5.1%}   "
            f"{result.rounds / result.campaigns:>8.2f}   "
            f"{result.bird_actions / result.campaigns:>6.1f}/"
            f"{result.sea_actions / result.campaigns:<6.1f}"
        )
    wins = sum(result.bird_wins for result in results)
    campaigns = sum(result.campaigns for result in results)
    print(f"\nOverall Bird win rate: {wins / campaigns:.1%} across {campaigns} campaigns")
    bird_starts = sum(result.bird_starts for result in results)
    sea_starts = campaigns - bird_starts
    bird_start_wins = sum(result.bird_wins_when_starting for result in results)
    sea_start_wins = sum(result.sea_wins_when_starting for result in results)
    bird_start_rate = bird_start_wins / bird_starts if bird_starts else 0.0
    sea_start_rate = sea_start_wins / sea_starts if sea_starts else 0.0
    print(
        "Opening-player campaign win rate: "
        f"{(bird_start_wins + sea_start_wins) / campaigns:.1%} "
        f"(Bird starts {bird_start_rate:.1%}; Sea starts {sea_start_rate:.1%})"
    )
    strategy_names = sorted(
        {result.bird_strategy for result in results} | {result.sea_strategy for result in results}
    )
    print("Faction-balanced strategy win rates:")
    for name in strategy_names:
        strategy_wins = sum(
            result.bird_wins if result.bird_strategy == name else 0 for result in results
        ) + sum(
            result.campaigns - result.bird_wins if result.sea_strategy == name else 0
            for result in results
        )
        strategy_campaigns = sum(
            result.campaigns if result.bird_strategy == name else 0 for result in results
        ) + sum(result.campaigns if result.sea_strategy == name else 0 for result in results)
        print(f"  {name:<16} {strategy_wins / strategy_campaigns:.1%} ({strategy_campaigns} games)")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Spy Web AI-vs-AI strategy benchmarks")
    parser.add_argument("--campaigns", type=int, default=10, help="campaigns per matrix cell")
    parser.add_argument("--boards", type=int, default=50_000, help="boards per faction universe")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/benchmark"))
    parser.add_argument(
        "--strategies",
        default="frugal,current,tempo",
        help=f"comma-separated strategies: {','.join(STRATEGIES)}",
    )
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--max-depth",
        type=int,
        help="override adaptive search depth for faster exploratory sweeps",
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> tuple[Aggregate, ...]:
    args = _parse_args(argv)
    names = args.strategies.split(",")
    try:
        strategies = [_with_max_depth(STRATEGIES[name], args.max_depth) for name in names]
    except KeyError as error:
        raise SystemExit(f"Unknown strategy: {error.args[0]}") from error
    print(f"Loading {args.boards:,}-board Bird and Sea benchmark universes...")
    assets = load_assets(args.cache_dir, args.boards)
    results = run_matrix(
        assets,
        strategies,
        campaigns=args.campaigns,
        seed=args.seed,
        progress=True,
    )
    _print_results(results)
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(result) for result in results], indent=2) + "\n"
        args.json_out.write_text(payload)
    return results


def main() -> None:
    run()
