from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from spyweb.core.catalog import FIXTURE_RULES
from spyweb.core.events import (
    AccusationResolved,
    ObservedEvent,
    QuestionAnswered,
    SecondAnswerBought,
)
from spyweb.core.model import (
    Answer,
    CityId,
    LandmarkAnswer,
    NothingAnswer,
    Question,
    Sense,
    SpyAnswer,
)
from spyweb.solver.belief import (
    full_belief,
    pair_candidates,
    pair_count,
    rank_questions,
    score_dual_payment,
)
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


def _parse_question() -> Question:
    spy_name = input("Spy: ").strip().lower()
    spy = next((item for item in FIXTURE_RULES.spies if item.name.lower() == spy_name), None)
    if spy is None:
        raise ValueError(f"Unknown spy: {spy_name}")
    try:
        sense = Sense[input("Sense (look/hear/point): ").strip().upper()]
    except KeyError as error:
        raise ValueError("Sense must be look, hear, or point") from error
    return Question(spy.id, sense)


def _parse_city(raw: str) -> CityId:
    value = raw.strip().lower()
    city = next((item for item in FIXTURE_RULES.cities if item.name.lower() == value), None)
    if city is None:
        raise ValueError(f"Unknown city: {raw}")
    return city.id


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
    history = [state]
    while True:
        print(f"\nPossible boards: {state.belief.size:,}")
        print(f"Possible ringleader/hideout pairs: {pair_count(universe, state.belief)}")
        ranking = rank_questions(universe, state.belief)
        for score in ranking[:5]:
            question = encoding.decode_question(score.question)
            spy_name = FIXTURE_RULES.spies[int(question.spy)].name
            print(
                f"  {spy_name} {question.sense.name.lower()}: "
                f"worst {score.worst_pairs} pairs / {score.worst_boards:,} boards"
            )
        command = (
            input(
                "\n[a]nswer, [s]econd answer, accusation [x], "
                "[p]artitions, [c]andidates, [t]race, [u]ndo, [q]uit: "
            )
            .strip()
            .lower()
        )
        if command == "q":
            return
        if command == "p":
            best = ranking[0]
            question = encoding.decode_question(best.question)
            print(
                f"\n{FIXTURE_RULES.spies[int(question.spy)].name} "
                f"{question.sense.name.lower()} partitions:"
            )
            for partition in sorted(best.partitions, key=lambda item: item.boards, reverse=True):
                print(
                    f"  {_answer_label(encoding.decode_answer(partition.answer))}: "
                    f"{partition.pairs} pairs / {partition.boards:,} boards"
                )
            if universe.dual_question[int(best.question)]:
                print("\nIf the opponent reveals each first answer:")
                for option in score_dual_payment(universe, state.belief, best.question):
                    print(
                        f"  {_answer_label(encoding.decode_answer(option.first))}: "
                        f"no pay {option.no_pay_pairs} pairs / {option.no_pay_boards:,} boards; "
                        f"pay worst case {option.paid_worst_pairs} pairs / "
                        f"{option.paid_worst_boards:,} boards"
                    )
            continue
        if command == "c":
            candidates = sorted(
                pair_candidates(universe, state.belief), key=lambda item: item.boards, reverse=True
            )
            for candidate in candidates:
                print(
                    f"  {FIXTURE_RULES.spies[candidate.ringleader].name} in "
                    f"{FIXTURE_RULES.cities[candidate.hideout].name}: {candidate.boards:,} boards"
                )
            continue
        if command == "t":
            for step in state.trace:
                print(
                    f"{step.sequence}. {type(step.event).__name__}: "
                    f"{step.boards_before:,} -> {step.boards_after:,} boards, "
                    f"{step.pairs_before} -> {step.pairs_after} pairs"
                )
            continue
        if command == "u":
            if len(history) > 1:
                history.pop()
                state = history[-1]
                print("Undid last event")
            else:
                print("Nothing to undo")
            continue
        try:
            event: ObservedEvent
            if command == "a":
                question = _parse_question()
                answer = _parse_answer(input("Answer (spy, landmark, or Nothing): "))
                event = QuestionAnswered(question, answer)
            elif command == "s":
                question = _parse_question()
                first = _parse_answer(input("First answer: "))
                second = _parse_answer(input("Paid second answer: "))
                event = SecondAnswerBought(question, first, second)
            elif command == "x":
                spy_name = input("Accused ringleader: ").strip().lower()
                spy = next(
                    (item for item in FIXTURE_RULES.spies if item.name.lower() == spy_name), None
                )
                if spy is None:
                    raise ValueError(f"Unknown spy: {spy_name}")
                hideout = _parse_city(input("Accused hideout: "))
                correct = input("Correct? [y/N]: ").strip().lower() == "y"
                event = AccusationResolved(spy.id, hideout, correct)
            else:
                continue
        except ValueError as error:
            print(error)
            continue
        next_state = apply_event(universe, encoding, state, event)
        if next_state.belief.size == 0:
            print("Rejected: that observation contradicts every remaining board")
            continue
        state = next_state
        history.append(state)
        print(f"Recorded {type(event).__name__}")


def main() -> None:
    run()
