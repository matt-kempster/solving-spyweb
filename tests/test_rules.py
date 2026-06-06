from spyweb.core.catalog import FIXTURE_RULES
from spyweb.core.model import (
    Board,
    CityId,
    LandmarkAnswer,
    NothingAnswer,
    Question,
    Sense,
    SpyId,
)
from spyweb.core.rules import answer_question, validate_board


def test_resolves_visible_landmark_hideout_and_ringleader_answers() -> None:
    board = Board(
        SpyId(8),
        CityId(4),
        (SpyId(0), SpyId(1), SpyId(2), SpyId(3), None, SpyId(4), SpyId(5), SpyId(6), SpyId(7)),
    )
    validate_board(FIXTURE_RULES, board)
    assert answer_question(FIXTURE_RULES, board, Question(SpyId(0), Sense.LOOK)) == (
        LandmarkAnswer(FIXTURE_RULES.landmarks[0].id),
    )
    assert answer_question(FIXTURE_RULES, board, Question(SpyId(1), Sense.POINT)) == (
        NothingAnswer(),
    )
    assert answer_question(FIXTURE_RULES, board, Question(SpyId(8), Sense.LOOK)) == (
        NothingAnswer(),
    )
