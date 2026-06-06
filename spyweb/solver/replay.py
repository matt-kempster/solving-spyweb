from dataclasses import dataclass

import numpy as np

from spyweb.core.events import (
    AccusationResolved,
    QuestionAnswered,
    SecondAnswerBought,
    Trace,
    TraceStep,
)
from spyweb.solver.belief import Belief, filter_first_answer, filter_paid_second, pair_count
from spyweb.solver.encoding import Encoding
from spyweb.solver.universe import Universe


@dataclass(frozen=True)
class ReplayState:
    belief: Belief
    trace: Trace = ()


def apply_event(
    universe: Universe, encoding: Encoding, state: ReplayState, event: object
) -> ReplayState:
    before = state.belief
    after = before
    if isinstance(event, QuestionAnswered):
        after = filter_first_answer(
            universe,
            before,
            encoding.question_id(event.question),
            encoding.answer_code(event.answer),
        )
    elif isinstance(event, SecondAnswerBought):
        after = filter_paid_second(
            universe,
            before,
            encoding.question_id(event.question),
            encoding.answer_code(event.first),
            encoding.answer_code(event.second),
        )
    elif isinstance(event, AccusationResolved):
        matches = (universe.ringleader[before] == event.ringleader) & (
            universe.hideout[before] == event.hideout
        )
        after = before[matches if event.correct else np.logical_not(matches)]
    else:
        raise TypeError("Unsupported observed event")
    step = TraceStep(
        len(state.trace) + 1,
        event,
        int(before.size),
        int(after.size),
        pair_count(universe, before),
        pair_count(universe, after),
    )
    return ReplayState(after, (*state.trace, step))
