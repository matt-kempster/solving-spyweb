from dataclasses import replace

import numpy as np

from spyweb.ai import AiKnowledge, AiStrategy
from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import (
    CAMPAIGN_TARGET,
    TurnPhase,
    accuse,
    ask_question,
    legal_questions,
    new_campaign,
)
from spyweb.core.model import SpyAnswer
from spyweb.core.rules import answer_question, validate_board
from spyweb.solver.belief import full_belief
from spyweb.solver.encoding import Encoding
from spyweb.solver.universe import build_universe
from spyweb.web import WebSession, project_campaign


def test_projection_only_reveals_viewers_private_board() -> None:
    campaign = new_campaign("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=4)

    record = project_campaign(campaign, 0)
    players = record["players"]

    assert isinstance(players, list)
    assert isinstance(players[0], dict) and "board" in players[0]
    assert isinstance(players[1], dict) and "board" not in players[1]
    assert isinstance(record["ownCards"], list)
    assert isinstance(record["opponentCards"], list)
    assert all(isinstance(card, dict) and "faction" in card for card in record["opponentCards"])
    assert isinstance(record["landmarks"], list)
    assert {
        (item["name"], item["row"], item["col"])
        for item in record["landmarks"]
        if isinstance(item, dict)
    } == {
        ("Car", 0, -1),
        ("Plane", -1, 2),
        ("Boat", 2, 3),
    }
    deductions = record["deductions"]
    assert isinstance(deductions, list)
    assert len(deductions) == 2
    assert record["roundReveal"] is None


def test_projection_reveals_both_boards_after_round_end() -> None:
    campaign = new_campaign("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=4)
    state = campaign.round
    target = state.players[1].board
    campaign = campaign.__class__(accuse(state, target.ringleader, target.hideout))

    record = project_campaign(campaign, 0)

    reveal = record["roundReveal"]
    assert isinstance(reveal, list)
    assert reveal == [
        {
            "player": 0,
            "ringleader": state.players[0].rules.spies[int(state.players[0].board.ringleader)].name,
            "hideout": state.players[0].rules.cities[int(state.players[0].board.hideout)].name,
            "board": record["players"][0]["board"],
        },
        {
            "player": 1,
            "ringleader": state.players[1].rules.spies[int(state.players[1].board.ringleader)].name,
            "hideout": state.players[1].rules.cities[int(state.players[1].board.hideout)].name,
            "board": [
                {
                    "id": int(city.id),
                    "city": city.name,
                    "occupant": (
                        "HIDEOUT"
                        if state.players[1].board.occupant_by_city[int(city.id)] is None
                        else state.players[1].rules.spies[
                            int(state.players[1].board.occupant_by_city[int(city.id)])
                        ].name
                    ),
                }
                for city in state.players[1].rules.cities
            ],
        },
    ]


def test_projection_builds_event_derived_deduction_graph() -> None:
    campaign = new_campaign("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=4)
    state = campaign.round
    question = next(
        question
        for question in legal_questions(SEA_RULES)
        if isinstance(answer_question(SEA_RULES, state.players[1].board, question)[0], SpyAnswer)
    )
    campaign = campaign.__class__(ask_question(state, question))

    record = project_campaign(campaign, 0)
    deductions = record["deductions"]
    assert isinstance(deductions, list)
    bird = deductions[0]
    assert isinstance(bird, dict)
    edges = bird["edges"]
    assert isinstance(edges, list)
    assert len(edges) == 1
    edge = edges[0]
    assert isinstance(edge, dict)
    assert edge["spy"] == SEA_RULES.spies[int(question.spy)].name
    assert edge["sense"] == question.sense.name.lower()


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


def test_web_session_ends_campaign_immediately_after_winning_accusation() -> None:
    campaign = new_campaign("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=4)
    target = campaign.round.players[1].board
    bounty = campaign.round.players[1].rules.spies[int(target.ringleader)].bounty
    players = list(campaign.round.players)
    players[0] = replace(players[0], money=CAMPAIGN_TARGET - bounty)
    campaign = replace(campaign, round=replace(campaign.round, players=(players[0], players[1])))
    session = WebSession(campaign)

    session.apply(
        {
            "type": "accuse",
            "player": 0,
            "ringleader": int(target.ringleader),
            "hideout": int(target.hideout),
        }
    )

    assert session.campaign.winner == 0
    assert session.project(0)["campaignWinner"] == 0


def test_web_ai_advances_until_human_input_or_turn() -> None:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    session = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4),
        ai_knowledge=knowledge,
    )

    question = session.project(0)["questions"]
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
    session.apply({"type": "end_turn", "player": 0})

    assert session.campaign.round.turn == 0 or session.ai_pending_question is not None
    assert session.ai_knowledge is not None
    assert session.ai_knowledge.belief.size < np.uint32(universe.board_count)


def test_web_ai_can_switch_to_component_strategy() -> None:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    session = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4),
        ai_knowledge=knowledge,
    )

    session.apply({"type": "set_ai_strategy", "player": 0, "strategy": "component"})

    assert session.ai_strategy is AiStrategy.COMPONENT
    assert session.project(0)["aiStrategy"] == "component"


def test_web_ai_can_switch_to_tempo_strategy() -> None:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    session = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4),
        ai_knowledge=knowledge,
    )

    session.apply({"type": "set_ai_strategy", "player": 0, "strategy": "tempo"})

    assert session.ai_strategy is AiStrategy.TEMPO
    assert session.project(0)["aiStrategy"] == "tempo"


def test_web_ai_can_switch_to_human_strategy() -> None:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    session = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4),
        ai_knowledge=knowledge,
    )

    session.apply({"type": "set_ai_strategy", "player": 0, "strategy": "human"})

    assert session.ai_strategy is AiStrategy.HUMAN
    assert session.project(0)["aiStrategy"] == "human"


def test_web_ai_can_switch_to_prior_strategy() -> None:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    session = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4),
        ai_knowledge=knowledge,
    )

    session.apply({"type": "set_ai_strategy", "player": 0, "strategy": "prior"})

    assert session.ai_strategy is AiStrategy.PRIOR
    assert session.project(0)["aiStrategy"] == "prior"


def test_ai_projection_rejects_ai_private_view() -> None:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=100)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    campaign = new_campaign("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4)

    try:
        project_campaign(campaign, 1, ai_knowledge=knowledge)
    except ValueError as error:
        assert str(error) == "The AI's private board is not viewable"
    else:
        raise AssertionError("AI private state must not be projected")


def test_ai_projection_supports_human_sea_and_ai_bird() -> None:
    encoding = Encoding(SEA_RULES)
    universe = build_universe(SEA_RULES, encoding, limit=100)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    campaign = new_campaign("Bird AI", BIRD_RULES, "Sea", SEA_RULES, seed=4)
    session = WebSession(
        campaign,
        ai_knowledge=knowledge,
        human_player=1,
        ai_player=0,
    )

    record = session.project(1)

    assert record["viewer"] == 1
    assert record["humanPlayer"] == 1
    assert record["aiPlayer"] == 0
    assert record["ownCards"][0]["faction"] == "sea"
    assert record["opponentCards"][0]["faction"] == "bird"
    try:
        session.project(0)
    except ValueError as error:
        assert str(error) == "The AI's private board is not viewable"
    else:
        raise AssertionError("AI private state must not be projected")


def _occupant_payload(session: WebSession, player: int) -> list[int]:
    board = session.campaign.round.players[player].board
    return [-1 if occupant is None else int(occupant) for occupant in board.occupant_by_city]


def test_web_setup_blocks_play_until_both_layouts_are_locked() -> None:
    session = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea", SEA_RULES, seed=4),
        setup_enabled=True,
    )
    session.prepare_setup()

    projected = session.project(0)
    assert projected["setupEnabled"] is True
    assert projected["setupComplete"] is False
    assert projected["setupReady"] == [False, False]

    first_question = projected["questions"]
    assert isinstance(first_question, list)
    question = first_question[0]
    assert isinstance(question, dict)
    try:
        session.apply(
            {
                "type": "ask",
                "player": 0,
                "spy": question["spy"],
                "sense": question["sense"],
                "firstAnswerIndex": 0,
            }
        )
    except ValueError as error:
        assert str(error) == "Both players must lock their layouts before play"
    else:
        raise AssertionError("Unready setup should block normal play")

    session.apply({"type": "set_layout", "player": 0, "occupants": _occupant_payload(session, 0)})
    assert session.project(0)["setupReady"] == [True, False]

    session.apply({"type": "set_layout", "player": 1, "occupants": _occupant_payload(session, 1)})
    assert session.project(0)["setupComplete"] is True


def test_web_ai_setup_locks_varied_ai_layout_without_advancing() -> None:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    session = WebSession(
        new_campaign("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4),
        seed=None,
        ai_knowledge=knowledge,
        setup_enabled=True,
    )
    original_board = session.campaign.round.players[1].board

    session.prepare_setup()

    ai_board = session.campaign.round.players[1].board
    assert session.project(0)["setupReady"] == [False, True]
    assert ai_board.ringleader == original_board.ringleader
    validate_board(SEA_RULES, ai_board)

    session.advance_ai()
    assert session.campaign.round.history == ()

    session.apply({"type": "set_layout", "player": 0, "occupants": _occupant_payload(session, 0)})
    assert session.project(0)["setupComplete"] is True


def test_web_ai_setup_supports_ai_bird() -> None:
    encoding = Encoding(SEA_RULES)
    universe = build_universe(SEA_RULES, encoding, limit=2_000)
    knowledge = AiKnowledge(universe, encoding, full_belief(universe))
    session = WebSession(
        new_campaign("Bird AI", BIRD_RULES, "Sea", SEA_RULES, seed=4),
        seed=None,
        ai_knowledge=knowledge,
        human_player=1,
        ai_player=0,
        setup_enabled=True,
    )
    original_board = session.campaign.round.players[0].board

    session.prepare_setup()

    ai_board = session.campaign.round.players[0].board
    assert session.project(1)["setupReady"] == [True, False]
    assert ai_board.ringleader == original_board.ringleader
    validate_board(BIRD_RULES, ai_board)

    session.apply({"type": "set_layout", "player": 1, "occupants": _occupant_payload(session, 1)})
    assert session.project(1)["setupComplete"] is True
