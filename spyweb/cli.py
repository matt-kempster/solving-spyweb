from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from spyweb.audit import read_trace_events, write_trace
from spyweb.core.catalog import BIRD_RULES, SEA_RULES
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
    Rules,
    Sense,
    SpyAnswer,
)
from spyweb.core.rules import rules_fingerprint
from spyweb.core.rules_io import read_rules, write_rules
from spyweb.solver.belief import (
    full_belief,
    pair_candidates,
    pair_count,
    score_dual_payment,
)
from spyweb.solver.encoding import Encoding
from spyweb.solver.policy import recommend_questions
from spyweb.solver.replay import ReplayState, apply_event
from spyweb.solver.universe import Universe, build_universe, universe_board_count


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Spy Web solving assistant")
    parser.add_argument(
        "--boards", type=int, default=50_000, help="boards to build; use 3265920 for all"
    )
    parser.add_argument("--cache", type=Path, help="optional .npz universe cache")
    parser.add_argument(
        "--faction",
        choices=("bird", "sea"),
        default="bird",
        help="opponent faction to solve when --rules is not supplied",
    )
    parser.add_argument("--rules", type=Path, help="load a versioned rules transcription JSON")
    parser.add_argument("--export-rules", type=Path, help="export selected bundled rules and exit")
    parser.add_argument("--trace-in", type=Path, help="load and replay an audit JSON trace")
    parser.add_argument("--trace-out", type=Path, help="write accepted events as audit JSON")
    parser.add_argument(
        "--lookahead-depth",
        type=int,
        default=1,
        help="adversarial question lookahead depth; deeper search starts only on small beliefs",
    )
    parser.add_argument(
        "--lookahead-max-boards",
        type=int,
        default=10_000,
        help="maximum belief size eligible for deeper lookahead",
    )
    return parser.parse_args(argv)


def _answer_label(rules: Rules, answer: Answer) -> str:
    if isinstance(answer, NothingAnswer):
        return "Nothing"
    if isinstance(answer, SpyAnswer):
        return rules.spies[int(answer.spy)].name
    return rules.landmarks[int(answer.landmark)].name


def _parse_answer(rules: Rules, raw: str) -> Answer:
    value = raw.strip().lower()
    if value == "nothing":
        return NothingAnswer()
    spy = next((item for item in rules.spies if item.name.lower() == value), None)
    if spy is not None:
        return SpyAnswer(spy.id)
    landmark = next((item for item in rules.landmarks if item.name.lower() == value), None)
    if landmark is not None:
        return LandmarkAnswer(landmark.id)
    raise ValueError(f"Unknown answer: {raw}")


def _parse_question(rules: Rules) -> Question:
    spy_name = input("Spy: ").strip().lower()
    spy = next((item for item in rules.spies if item.name.lower() == spy_name), None)
    if spy is None:
        raise ValueError(f"Unknown spy: {spy_name}")
    try:
        sense = Sense[input("Sense (look/hear/point): ").strip().upper()]
    except KeyError as error:
        raise ValueError("Sense must be look, hear, or point") from error
    if not spy.directions[sense]:
        raise ValueError(f"{spy.name} cannot {sense.name.lower()}")
    return Question(spy.id, sense)


def _parse_city(rules: Rules, raw: str) -> CityId:
    value = raw.strip().lower()
    city = next((item for item in rules.cities if item.name.lower() == value), None)
    if city is None:
        raise ValueError(f"Unknown city: {raw}")
    return city.id


def _load_or_build(args: argparse.Namespace, rules: Rules, encoding: Encoding) -> Universe:
    cache: Path | None = args.cache
    if cache is not None and cache.exists():
        print(f"Loading universe from {cache}...")
        return Universe.load(
            cache,
            expected_rules_fingerprint=rules_fingerprint(rules),
            expected_board_count=universe_board_count(rules, args.boards),
        )
    print(f"Building a {args.boards:,}-board universe...")
    universe = build_universe(rules, encoding, args.boards)
    if cache is not None:
        universe.save(cache)
    return universe


def run(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    bundled_rules = BIRD_RULES if args.faction == "bird" else SEA_RULES
    rules = bundled_rules if args.rules is None else read_rules(args.rules)
    if args.export_rules is not None:
        write_rules(rules, args.export_rules)
        print(f"Wrote rules transcription to {args.export_rules}")
        return
    encoding = Encoding(rules)
    universe = _load_or_build(args, rules, encoding)
    state = ReplayState(full_belief(universe))
    history = [state]
    if args.trace_in is not None:
        print(f"Replaying trace from {args.trace_in}...")
        for saved_event in read_trace_events(args.trace_in, rules):
            state = apply_event(universe, encoding, state, saved_event)
            if state.belief.size == 0:
                raise ValueError(
                    f"Trace event {len(state.trace)} contradicts every remaining board"
                )
            history.append(state)
        print(f"Replayed {len(state.trace)} events")
    while True:
        print(f"\nPossible boards: {state.belief.size:,}")
        print(f"Possible ringleader/hideout pairs: {pair_count(universe, state.belief)}")
        recommendation = recommend_questions(
            universe,
            state.belief,
            depth=args.lookahead_depth,
            max_lookahead_boards=args.lookahead_max_boards,
        )
        if recommendation.effective_depth != recommendation.requested_depth:
            print(
                f"Policy: depth 1 fallback; depth {recommendation.requested_depth} starts at "
                f"{args.lookahead_max_boards:,} boards"
            )
        else:
            print(f"Policy: adversarial depth {recommendation.effective_depth}")
        for policy_score in recommendation.scores[:5]:
            score = policy_score.immediate
            question = encoding.decode_question(score.question)
            spy_name = rules.spies[int(question.spy)].name
            suffix = ""
            if recommendation.effective_depth > 1:
                suffix = (
                    f"; depth-{recommendation.effective_depth} worst "
                    f"{policy_score.worst_leaf_pairs} pairs / "
                    f"{policy_score.worst_leaf_boards:,} boards"
                )
            print(
                f"  {spy_name} {question.sense.name.lower()}: immediate worst "
                f"{score.worst_pairs} pairs / {score.worst_boards:,} boards{suffix}"
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
            best = recommendation.best.immediate
            question = encoding.decode_question(best.question)
            print(
                f"\n{rules.spies[int(question.spy)].name} "
                f"{question.sense.name.lower()} partitions:"
            )
            for partition in sorted(best.partitions, key=lambda item: item.boards, reverse=True):
                print(
                    f"  {_answer_label(rules, encoding.decode_answer(partition.answer))}: "
                    f"{partition.pairs} pairs / {partition.boards:,} boards"
                )
            if universe.dual_question[int(best.question)]:
                print("\nIf the opponent reveals each first answer:")
                for option in score_dual_payment(universe, state.belief, best.question):
                    print(
                        f"  {_answer_label(rules, encoding.decode_answer(option.first))}: "
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
                    f"  {rules.spies[candidate.ringleader].name} in "
                    f"{rules.cities[candidate.hideout].name}: {candidate.boards:,} boards"
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
                if args.trace_out is not None:
                    write_trace(state.trace, args.trace_out, rules)
                print("Undid last event")
            else:
                print("Nothing to undo")
            continue
        try:
            event: ObservedEvent
            if command == "a":
                question = _parse_question(rules)
                answer = _parse_answer(rules, input("Answer (spy, landmark, or Nothing): "))
                event = QuestionAnswered(question, answer)
            elif command == "s":
                question = _parse_question(rules)
                first = _parse_answer(rules, input("First answer: "))
                second = _parse_answer(rules, input("Paid second answer: "))
                event = SecondAnswerBought(question, first, second)
            elif command == "x":
                spy_name = input("Accused ringleader: ").strip().lower()
                spy = next(
                    (item for item in rules.spies if item.name.lower() == spy_name), None
                )
                if spy is None:
                    raise ValueError(f"Unknown spy: {spy_name}")
                hideout = _parse_city(rules, input("Accused hideout: "))
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
        if args.trace_out is not None:
            write_trace(state.trace, args.trace_out, rules)
        print(f"Recorded {type(event).__name__}")


def main() -> None:
    run()
