from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from spyweb.core.catalog import FIXTURE_RULES
from spyweb.core.events import QuestionAnswered
from spyweb.core.model import Answer, LandmarkAnswer, NothingAnswer, Question, Sense, SpyAnswer
from spyweb.solver.belief import full_belief, pair_count, rank_questions
from spyweb.solver.encoding import Encoding
from spyweb.solver.replay import ReplayState, apply_event
from spyweb.solver.universe import Universe, build_universe


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Spy Web solving assistant")
    parser.add_argument(
        "--boards", type=int, default=50_000, help="boards to build; use 3265920 for all"
    )
    parser.add_argument("--cache", type=Path, help="optional .npz universe cache")
    return parser.parse_args(argv)


def _answer_label(answer: Answer) -> str:
    if isinstance(answer, NothingAnswer):
        return "Nothing"
    if isinstance(answer, SpyAnswer):
        return FIXTURE_RULES.spies[int(answer.spy)].name
    return FIXTURE_RULES.landmarks[int(answer.landmark)].name


def _parse_answer(raw: str) -> Answer:
    value = raw.strip().lower()
    if value == "nothing":
        return NothingAnswer()
    spy = next((item for item in FIXTURE_RULES.spies if item.name.lower() == value), None)
    if spy is not None:
        return SpyAnswer(spy.id)
    landmark = next((item for item in FIXTURE_RULES.landmarks if item.name.lower() == value), None)
    if landmark is not None:
        return LandmarkAnswer(landmark.id)
    raise ValueError(f"Unknown answer: {raw}")


def _load_or_build(args: argparse.Namespace, encoding: Encoding) -> Universe:
    cache: Path | None = args.cache
    if cache is not None and cache.exists():
        print(f"Loading universe from {cache}...")
        return Universe.load(cache)
    print(f"Building a {args.boards:,}-board development universe...")
    universe = build_universe(FIXTURE_RULES, encoding, args.boards)
    if cache is not None:
        universe.save(cache)
    return universe


def run(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    encoding = Encoding(FIXTURE_RULES)
    universe = _load_or_build(args, encoding)
    state = ReplayState(full_belief(universe))
    while True:
        print(f"\nPossible boards: {state.belief.size:,}")
        print(f"Possible ringleader/hideout pairs: {pair_count(universe, state.belief)}")
        for score in rank_questions(universe, state.belief)[:5]:
            question = encoding.decode_question(score.question)
            spy_name = FIXTURE_RULES.spies[int(question.spy)].name
            print(
                f"  {spy_name} {question.sense.name.lower()}: "
                f"worst {score.worst_pairs} pairs / {score.worst_boards:,} boards"
            )
        command = input("\n[a]dd observation, [t]race, [q]uit: ").strip().lower()
        if command == "q":
            return
        if command == "t":
            for step in state.trace:
                print(
                    f"{step.sequence}. {type(step.event).__name__}: "
                    f"{step.boards_before:,} -> {step.boards_after:,} boards, "
                    f"{step.pairs_before} -> {step.pairs_after} pairs"
                )
            continue
        if command != "a":
            continue
        spy_name = input("Spy: ").strip().lower()
        spy = next((item for item in FIXTURE_RULES.spies if item.name.lower() == spy_name), None)
        if spy is None:
            print("Unknown spy")
            continue
        try:
            sense = Sense[input("Sense (look/hear/point): ").strip().upper()]
            answer = _parse_answer(input("Answer (spy, landmark, or Nothing): "))
        except (KeyError, ValueError) as error:
            print(error)
            continue
        event = QuestionAnswered(Question(spy.id, sense), answer)
        state = apply_event(universe, encoding, state, event)
        print(f"Recorded {spy.name} {sense.name.lower()} = {_answer_label(answer)}")


def main() -> None:
    run()
