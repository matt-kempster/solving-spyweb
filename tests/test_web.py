from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import TurnPhase, new_campaign
from spyweb.web import WebSession, project_campaign


def test_projection_only_reveals_viewers_private_board() -> None:
    campaign = new_campaign("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=4)

    record = project_campaign(campaign, 0)
    players = record["players"]

    assert isinstance(players, list)
    assert isinstance(players[0], dict) and "board" in players[0]
    assert isinstance(players[1], dict) and "board" not in players[1]


def test_web_session_applies_question_and_turn_actions() -> None:
    session = WebSession(new_campaign("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=4))
    question = project_campaign(session.campaign, 0)["questions"]
    assert isinstance(question, list)
    first = question[0]
    assert isinstance(first, dict)

    session.apply(
        {
            "type": "ask",
            "player": 0,
            "spy": first["spy"],
            "sense": first["sense"],
            "firstAnswerIndex": 0,
        }
    )
    assert session.campaign.round.phase is TurnPhase.POST_ACTION

    session.apply({"type": "end_turn", "player": 0})
    assert session.campaign.round.turn == 1
