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
from spyweb.solver.component_policy import rank_component_questions
from spyweb.solver.encoding import Encoding
from spyweb.solver.eta import (
    SolveEta,
    estimate_solve_eta,
    expected_ringleader_bounty,
    extra_action_changes_race_winner,
    extra_action_improves_campaign_outcome,
)
from spyweb.solver.human_policy import rank_human_questions
from spyweb.solver.hybrid_policy import (
    EXACT_ENDGAME_MAX_PAIRS,
    exact_endgame_action,
    recommend_hybrid_questions,
    recommend_prior_questions,
)
from spyweb.solver.policy import recommend_questions
from spyweb.solver.simple_policy import best_non_nothing_question
from spyweb.solver.universe import Universe, build_universe, universe_board_count


class SearchPolicy(StrEnum):
    GREEDY = "greedy"
    ADAPTIVE = "adaptive"
    COMPONENT = "component"
    HUMAN = "human"
    HYBRID = "hybrid"
    PRIOR = "prior"
    NONNULL = "nonnull"


class SpendPolicy(StrEnum):
    NEVER = "never"
    TEMPO = "tempo"
    RACE = "race"


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
    "race": Strategy("race", SearchPolicy.ADAPTIVE, SpendPolicy.RACE, SetupPolicy.DEFENSIVE),
    "component": Strategy(
        "component",
        SearchPolicy.COMPONENT,
        SpendPolicy.TEMPO,
        SetupPolicy.DEFENSIVE,
    ),
    "human": Strategy("human", SearchPolicy.HUMAN, SpendPolicy.TEMPO, SetupPolicy.DEFENSIVE),
    "hybrid": Strategy("hybrid", SearchPolicy.HYBRID, SpendPolicy.TEMPO, SetupPolicy.DEFENSIVE),
    "prior": Strategy("prior", SearchPolicy.PRIOR, SpendPolicy.TEMPO, SetupPolicy.DEFENSIVE),
    "nonnull": Strategy(
        "nonnull", SearchPolicy.NONNULL, SpendPolicy.TEMPO, SetupPolicy.DEFENSIVE
    ),
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
    bird_extra_actions: int = 0
    sea_extra_actions: int = 0

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
        self.bird_extra_actions += metrics.extra_actions[0]
        self.sea_extra_actions += metrics.extra_actions[1]

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

    def sampled_knowledge_of(
        self,
        faction: Faction,
        *,
        true_board: int,
        boards: int,
        random: Random,
    ) -> AiKnowledge:
        knowledge = self.knowledge_of(faction)
        universe = knowledge.universe
        if boards <= 0 or boards >= universe.board_count:
            return knowledge
        if true_board < 0 or true_board >= universe.board_count:
            raise ValueError(f"True board is outside the {faction} universe: {true_board}")
        other_ids = random.sample(range(universe.board_count - 1), boards - 1)
        belief = np.fromiter(
            (
                board_id if board_id < true_board else board_id + 1
                for board_id in other_ids
            ),
            dtype=np.uint32,
            count=boards - 1,
        )
        belief = np.append(belief, np.uint32(true_board))
        return AiKnowledge(universe, knowledge.encoding, belief)


type Observation = tuple[int, ...]
type PolicyKey = tuple[Faction, SearchPolicy, int, int, tuple[Observation, ...]]
type PolicyCache = dict[PolicyKey, PairCandidate | Question]
type EtaKey = tuple[Faction, int, tuple[Observation, ...]]
type EtaCache = dict[EtaKey, SolveEta]


@dataclass(frozen=True)
class TrackedKnowledge:
    ai: AiKnowledge
    cache_scope: int = 0
    observations: tuple[Observation, ...] = ()

    def observed_first(self, question: Question, answer: Answer) -> TrackedKnowledge:
        qid = self.ai.encoding.question_id(question)
        code = self.ai.encoding.answer_code(answer)
        return TrackedKnowledge(
            observe_first(self.ai, question, answer),
            self.cache_scope,
            (*self.observations, (0, int(qid), int(code))),
        )

    def observed_second(
        self, question: Question, first: Answer, second: Answer
    ) -> TrackedKnowledge:
        qid = self.ai.encoding.question_id(question)
        first_code = self.ai.encoding.answer_code(first)
        second_code = self.ai.encoding.answer_code(second)
        return TrackedKnowledge(
            observe_second(self.ai, question, first, second),
            self.cache_scope,
            (*self.observations, (1, int(qid), int(first_code), int(second_code))),
        )

    def observed_accusation(self, event: Accusation) -> TrackedKnowledge:
        return TrackedKnowledge(
            observe_accusation(
                self.ai, event.ringleader, event.hideout, correct=event.correct
            ),
            self.cache_scope,
            (
                *self.observations,
                (2, int(event.ringleader), int(event.hideout), int(event.correct)),
            ),
        )


def _estimate_eta(knowledge: TrackedKnowledge, cache: EtaCache) -> SolveEta:
    key = (
        knowledge.ai.encoding.rules.spies[0].faction,
        knowledge.cache_scope,
        knowledge.observations,
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    eta = estimate_solve_eta(knowledge.ai.universe, knowledge.ai.belief)
    cache[key] = eta
    return eta


def _should_buy_race_extra(
    state: GameState,
    knowledge: list[TrackedKnowledge],
    eta_cache: EtaCache,
) -> bool:
    if state.extra_action_bought or state.actor.money < ACTION_COST:
        return False
    actor = state.turn
    changes_winner = extra_action_changes_race_winner(
        _estimate_eta(knowledge[actor], eta_cache), _estimate_eta(knowledge[1 - actor], eta_cache)
    )
    if not changes_winner:
        return False
    return extra_action_improves_campaign_outcome(
        actor_money=state.actor.money,
        opponent_money=state.opponent.money,
        actor_win_bounty=expected_ringleader_bounty(
            knowledge[actor].ai.universe,
            knowledge[actor].ai.belief,
            state.opponent.rules,
        ),
        opponent_win_bounty=state.actor.rules.spies[int(state.actor.board.ringleader)].bounty,
    )


def _layout_score(universe: Universe, encoding: Encoding, board_id: int) -> tuple[int, int]:
    answers = universe.answer0[:, board_id]
    nothing = int(np.count_nonzero(answers == encoding.nothing))
    distinct = int(np.unique(answers).size)
    return nothing, -distinct


def _choose_board(
    universe: Universe, encoding: Encoding, strategy: Strategy, random: Random
) -> Board:
    return universe.board(_choose_board_id(universe, encoding, strategy, random))


def _choose_board_id(
    universe: Universe, encoding: Encoding, strategy: Strategy, random: Random
) -> int:
    ringleader = random.randrange(len(encoding.rules.spies))
    eligible = np.flatnonzero(universe.ringleader == ringleader)
    if not eligible.size:
        raise ValueError(f"Universe contains no boards for ringleader {ringleader}")
    if strategy.setup is SetupPolicy.RANDOM:
        return int(random.choice(eligible))
    sample_count = min(strategy.defensive_samples, int(eligible.size))
    candidates = [int(random.choice(eligible)) for _ in range(sample_count)]
    best_score = max(_layout_score(universe, encoding, board_id) for board_id in candidates)
    pool = [
        board_id
        for board_id in candidates
        if _layout_score(universe, encoding, board_id) == best_score
    ]
    return random.choice(pool)


def _choose_action(
    knowledge: TrackedKnowledge, strategy: Strategy, cache: PolicyCache
) -> PairCandidate | Question:
    faction = knowledge.ai.encoding.rules.spies[0].faction
    key = (
        faction,
        strategy.search,
        strategy.max_depth,
        knowledge.cache_scope,
        knowledge.observations,
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    ai = knowledge.ai
    candidates = pair_candidates(ai.universe, ai.belief)
    if len(candidates) == 1:
        cache[key] = candidates[0]
        return candidates[0]
    if strategy.search is SearchPolicy.COMPONENT:
        component_score = rank_component_questions(
            ai.universe,
            ai.encoding,
            ai.belief,
            knowledge.observations,
        )[0]
        component_action: PairCandidate | Question = ai.encoding.decode_question(
            component_score.immediate.question
        )
        cache[key] = component_action
        return component_action
    if strategy.search is SearchPolicy.HUMAN:
        human_score = rank_human_questions(
            ai.universe,
            ai.encoding,
            ai.belief,
            knowledge.observations,
        )[0]
        human_action: PairCandidate | Question = ai.encoding.decode_question(
            human_score.immediate.question
        )
        cache[key] = human_action
        return human_action
    if strategy.search is SearchPolicy.NONNULL:
        score = best_non_nothing_question(
            ai.universe,
            ai.encoding,
            ai.belief,
            knowledge.observations,
        )
        nonnull_action = ai.encoding.decode_question(score.question)
        cache[key] = nonnull_action
        return nonnull_action
    if strategy.search in (SearchPolicy.HYBRID, SearchPolicy.PRIOR) and len(
        candidates
    ) <= EXACT_ENDGAME_MAX_PAIRS:
        exact = exact_endgame_action(ai.universe, ai.belief)
        if exact.accusation is not None:
            cache[key] = exact.accusation
            return exact.accusation
        if exact.question is None:
            raise RuntimeError("Exact endgame search returned no action")
        exact_question = ai.encoding.decode_question(exact.question.question)
        cache[key] = exact_question
        return exact_question
    depth = (
        ai_search_depth(int(ai.belief.size))
        if strategy.search in (SearchPolicy.ADAPTIVE, SearchPolicy.HYBRID, SearchPolicy.PRIOR)
        else 1
    )
    depth = min(depth, strategy.max_depth)
    recommendation = (
        recommend_prior_questions(
            ai.universe,
            ai.encoding,
            ai.belief,
            knowledge.observations,
            depth=depth,
            max_lookahead_boards=int(ai.belief.size),
            branching_limit=5,
        )
        if strategy.search is SearchPolicy.PRIOR
        else
        recommend_hybrid_questions(
            ai.universe,
            ai.encoding,
            ai.belief,
            knowledge.observations,
            depth=depth,
            max_lookahead_boards=int(ai.belief.size),
            branching_limit=5,
        )
        if strategy.search is SearchPolicy.HYBRID
        else recommend_questions(
            ai.universe,
            ai.belief,
            depth=depth,
            max_lookahead_boards=int(ai.belief.size),
            branching_limit=5,
        )
    )
    if recommendation.best.immediate.worst_pairs >= len(candidates):
        action: PairCandidate | Question = max(candidates, key=lambda candidate: candidate.boards)
    else:
        action = ai.encoding.decode_question(recommendation.best.immediate.question)
    cache[key] = action
    return action


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
) -> tuple[GameState, tuple[int, int]]:
    board_ids = (
        _choose_board_id(assets.bird, assets.bird_encoding, strategies[0], random),
        _choose_board_id(assets.sea, assets.sea_encoding, strategies[1], random),
    )
    state = GameState(
        (
            PlayerState(
                strategies[0].name,
                BIRD_RULES,
                assets.bird.board(board_ids[0]),
                money[0],
            ),
            PlayerState(
                strategies[1].name,
                SEA_RULES,
                assets.sea.board(board_ids[1]),
                money[1],
            ),
        ),
        turn=turn,
    )
    return state, board_ids


def _round_knowledge(
    assets: BenchmarkAssets,
    board_ids: tuple[int, int],
    *,
    belief_boards: int,
    random: Random,
    cache_scopes: tuple[int, int],
) -> list[TrackedKnowledge]:
    return [
        TrackedKnowledge(
            assets.sampled_knowledge_of(
                Faction.SEA,
                true_board=board_ids[1],
                boards=belief_boards,
                random=random,
            ),
            cache_scopes[0],
        ),
        TrackedKnowledge(
            assets.sampled_knowledge_of(
                Faction.BIRD,
                true_board=board_ids[0],
                boards=belief_boards,
                random=random,
            ),
            cache_scopes[1],
        ),
    ]


def simulate_campaign(
    assets: BenchmarkAssets,
    matchup: Matchup,
    *,
    seed: int,
    starting_player: int = 0,
    max_rounds: int = 100,
    max_actions_per_round: int = 1_000,
    policy_cache: PolicyCache | None = None,
    belief_boards: int = 1_000,
) -> CampaignMetrics:
    random = Random(seed)
    strategies = (matchup.bird, matchup.sea)
    cache: PolicyCache = {} if policy_cache is None else policy_cache
    eta_cache: EtaCache = {}
    state, board_ids = _new_round(
        assets, strategies, random, (100_000, 100_000), starting_player
    )
    exact_beliefs = belief_boards <= 0 or belief_boards >= assets.bird.board_count
    scopes = (0, 0) if exact_beliefs else (seed * 1_000, seed * 1_000 + 1)
    knowledge = _round_knowledge(
        assets,
        board_ids,
        belief_boards=belief_boards,
        random=random,
        cache_scopes=scopes,
    )
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
                ai = knowledge[state.turn].ai
                remaining = pair_count(ai.universe, ai.belief)
                raise RuntimeError(
                    f"Round exceeded {max_actions_per_round} actions; "
                    f"{state.actor.name} still has {remaining} target pairs"
                )
            if state.phase is TurnPhase.ACTION:
                action = _choose_action(knowledge[actor], strategy, cache)
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
                    knowledge[actor] = knowledge[actor].observed_accusation(event)
                else:
                    answers = answer_question(state.opponent.rules, state.opponent.board, action)
                    first_index = _adversarial_first_index(knowledge[actor].ai, action, answers)
                    state = ask_question(state, action, first_answer_index=first_index)
                    event = state.history[-1]
                    assert isinstance(event, AskedQuestion)
                    questions[actor] += 1
                    knowledge[actor] = knowledge[actor].observed_first(action, event.answer)
                continue
            if state.phase is TurnPhase.DUAL_SECOND_ANSWER:
                pending = state.pending_second
                event = state.history[-1]
                assert pending is not None and isinstance(event, AskedQuestion)
                buy = (
                    strategy.spend in (SpendPolicy.TEMPO, SpendPolicy.RACE)
                    and state.actor.money >= ACTION_COST
                    and _should_buy_second(knowledge[actor].ai, pending.question, event.answer)
                )
                if not buy:
                    state = decline_second_answer(state)
                    continue
                state = buy_second_answer(state)
                second = state.history[-1]
                assert isinstance(second, BoughtSecondAnswer)
                second_answers[actor] += 1
                knowledge[actor] = knowledge[actor].observed_second(
                    pending.question, event.answer, second.answer
                )
                continue
            assert state.phase is TurnPhase.POST_ACTION
            can_convert = accusation_candidate(knowledge[actor].ai) is not None
            buy_extra = (
                strategy.spend is SpendPolicy.TEMPO
                and can_convert
                and not state.extra_action_bought
                and state.actor.money >= ACTION_COST
            )
            if strategy.spend is SpendPolicy.RACE:
                buy_extra = _should_buy_race_extra(state, knowledge, eta_cache)
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
        state, board_ids = _new_round(assets, strategies, random, money, loser)
        scopes = (
            (0, 0)
            if exact_beliefs
            else (seed * 1_000 + round_number * 2, seed * 1_000 + round_number * 2 + 1)
        )
        knowledge = _round_knowledge(
            assets,
            board_ids,
            belief_boards=belief_boards,
            random=random,
            cache_scopes=scopes,
        )
    raise RuntimeError("Campaign exceeded round limit")


def run_matrix(
    assets: BenchmarkAssets,
    strategies: Sequence[Strategy],
    *,
    campaigns: int,
    seed: int,
    belief_boards: int = 1_000,
    progress: bool = False,
) -> tuple[Aggregate, ...]:
    results: list[Aggregate] = []
    policy_cache: PolicyCache = {}
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
                        policy_cache=policy_cache,
                        belief_boards=belief_boards,
                    )
                )
            results.append(aggregate)
    return tuple(results)


def _with_max_depth(strategy: Strategy, max_depth: int | None) -> Strategy:
    return strategy if max_depth is None else replace(strategy, max_depth=max_depth)


def _load_universe(
    rules: Rules, cache: Path, boards: int, *, use_cache: bool
) -> tuple[Universe, Encoding]:
    encoding = Encoding(rules)
    expected = universe_board_count(rules, boards)
    if use_cache and cache.exists():
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
    if use_cache:
        universe.save(cache)
    return universe, encoding


def load_assets(cache_dir: Path, boards: int, *, use_cache: bool = True) -> BenchmarkAssets:
    bird, bird_encoding = _load_universe(
        BIRD_RULES, cache_dir / f"bird-{boards}.npz", boards, use_cache=use_cache
    )
    sea, sea_encoding = _load_universe(
        SEA_RULES, cache_dir / f"sea-{boards}.npz", boards, use_cache=use_cache
    )
    return BenchmarkAssets(bird, sea, bird_encoding, sea_encoding)


def _print_results(results: Sequence[Aggregate]) -> None:
    print(
        "\nBird strategy      Sea strategy       Bird wins (95% CI)  "
        "Avg rounds  Actions B/S  Extras B/S"
    )
    for result in results:
        print(
            f"{result.bird_strategy:<18} {result.sea_strategy:<18} "
            f"{result.bird_win_rate:>6.1%} +/- {result.bird_win_ci95:>5.1%}   "
            f"{result.rounds / result.campaigns:>8.2f}   "
            f"{result.bird_actions / result.campaigns:>6.1f}/"
            f"{result.sea_actions / result.campaigns:<6.1f} "
            f"{result.bird_extra_actions / result.campaigns:>5.1f}/"
            f"{result.sea_extra_actions / result.campaigns:<5.1f}"
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
    parser.add_argument("--campaigns", type=int, default=100, help="campaigns per matrix cell")
    parser.add_argument(
        "--boards",
        type=int,
        default=universe_board_count(BIRD_RULES),
        help="boards per faction universe; defaults to every legal board",
    )
    parser.add_argument(
        "--belief-boards",
        type=int,
        default=1_000,
        help="hypotheses evaluated by each AI; use 0 for exact full-universe beliefs",
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/benchmark"))
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="build solver universes in memory without reading or writing cache files",
    )
    parser.add_argument(
        "--strategies",
        default="frugal,current,tempo,component,human,hybrid,prior,nonnull",
        help=f"comma-separated strategies: {','.join(STRATEGIES)}",
    )
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--max-depth",
        type=int,
        default=1,
        help="maximum policy search depth; defaults to 1 for high-throughput sweeps",
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> tuple[Aggregate, ...]:
    args = _parse_args(argv)
    names = args.strategies.split(",")
    try:
        strategies = [_with_max_depth(STRATEGIES[name], args.max_depth) for name in names]
    except KeyError as error:
        raise SystemExit(f"Unknown strategy: {error.args[0]}") from error
    cache_label = "without cache" if args.no_cache else f"using {args.cache_dir}"
    print(f"Loading {args.boards:,}-board Bird and Sea solver universes {cache_label}...")
    belief_label = (
        "exact full-universe beliefs"
        if args.belief_boards <= 0 or args.belief_boards >= args.boards
        else f"{args.belief_boards:,}-board sampled beliefs"
    )
    print(f"AI policy evaluation: {belief_label}")
    assets = load_assets(args.cache_dir, args.boards, use_cache=not args.no_cache)
    results = run_matrix(
        assets,
        strategies,
        campaigns=args.campaigns,
        seed=args.seed,
        belief_boards=args.belief_boards,
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
