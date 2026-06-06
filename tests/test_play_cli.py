from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import ask_question, legal_questions, new_game
from spyweb.core.model import Direction
from spyweb.play_cli import _card_lines, _direction_label, _knowledge_lines


def test_direction_legend_includes_dual_and_unavailable_senses() -> None:
    assert _direction_label((Direction.N, Direction.S)) == "N/S"
    assert _direction_label(()) == "-"
    assert any("Raven" in line and "N/S" in line for line in _card_lines(BIRD_RULES))
    assert any("Urchin" in line and "E/W" in line for line in _card_lines(SEA_RULES))


def test_knowledge_base_only_lists_players_own_observations() -> None:
    state = new_game("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=7)
    asked = ask_question(state, legal_questions(SEA_RULES)[0])

    assert _knowledge_lines(asked, 0) != ("  No observations yet.",)
    assert _knowledge_lines(asked, 1) == ("  No observations yet.",)
