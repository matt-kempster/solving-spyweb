import pytest

from spyweb.core.catalog import BIRD_RULES, FIXTURE_RULES, SEA_RULES
from spyweb.core.model import (
    Board,
    CityId,
    Direction,
    LandmarkAnswer,
    NothingAnswer,
    Question,
    Sense,
    SpyId,
)
from spyweb.core.rules import answer_question, validate_board, validate_rules


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


def test_supplied_catalog_preserves_unavailable_senses_and_eel_point() -> None:
    validate_rules(BIRD_RULES)
    validate_rules(SEA_RULES)
    assert BIRD_RULES.spies[0].directions[Sense.HEAR] == ()
    assert BIRD_RULES.spies[3].directions[Sense.HEAR] == (Direction.E,)
    assert SEA_RULES.spies[5].name == "Eel"
    assert SEA_RULES.spies[5].directions[Sense.LOOK] == ()
    assert SEA_RULES.spies[5].directions[Sense.HEAR] == ()
    assert SEA_RULES.spies[5].directions[Sense.POINT] == (Direction.S,)


def test_unavailable_sense_cannot_be_answered() -> None:
    board = Board(
        SpyId(8),
        CityId(4),
        (SpyId(0), SpyId(1), SpyId(2), SpyId(3), None, SpyId(4), SpyId(5), SpyId(6), SpyId(7)),
    )
    with pytest.raises(ValueError, match="Raven cannot hear"):
        answer_question(BIRD_RULES, board, Question(SpyId(0), Sense.HEAR))
