from pathlib import Path

from spyweb.core.catalog import FIXTURE_RULES
from spyweb.core.events import QuestionAnswered
from spyweb.core.model import LandmarkAnswer, Question, Sense, SpyId
from spyweb.solver.belief import full_belief, pair_candidates, pair_count, rank_questions
from spyweb.solver.encoding import Encoding
from spyweb.solver.replay import ReplayState, apply_event
from spyweb.solver.universe import Universe, build_universe


def test_scores_replays_and_round_trips_cache(tmp_path: Path) -> None:
    encoding = Encoding(FIXTURE_RULES)
    universe = build_universe(FIXTURE_RULES, encoding, 2_000)
    belief = full_belief(universe)
    assert pair_count(universe, belief) == 81
    assert len(pair_candidates(universe, belief)) == 81
    assert len(rank_questions(universe, belief)) == 27

    event = QuestionAnswered(
        Question(SpyId(0), Sense.LOOK), LandmarkAnswer(FIXTURE_RULES.landmarks[0].id)
    )
    state = apply_event(universe, encoding, ReplayState(belief), event)
    assert state.belief.size < belief.size
    assert state.trace[0].boards_after == state.belief.size

    cache = tmp_path / "universe.npz"
    universe.save(cache)
    loaded = Universe.load(cache)
    assert loaded.board_count == universe.board_count
    assert (loaded.answer0 == universe.answer0).all()
