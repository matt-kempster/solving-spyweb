from dataclasses import replace

from spyweb.ai import AiKnowledge, ai_search_depth, should_buy_extra_for_accusation
from spyweb.core.catalog import BIRD_RULES, SEA_RULES
from spyweb.core.game import CAMPAIGN_TARGET, GameState, TurnPhase, new_game
from spyweb.solver.belief import full_belief
from spyweb.solver.encoding import Encoding
from spyweb.solver.universe import build_universe


def _knowledge_with_one_pair() -> AiKnowledge:
    encoding = Encoding(BIRD_RULES)
    universe = build_universe(BIRD_RULES, encoding, limit=2_000)
    belief = full_belief(universe)
    first = belief[0]
    same_pair = belief[
        (universe.ringleader[belief] == universe.ringleader[first])
        & (universe.hideout[belief] == universe.hideout[first])
    ]
    return AiKnowledge(universe, encoding, same_pair)


def _ai_post_action_state(ai_money: int, opponent_money: int) -> GameState:
    state = new_game("Bird", BIRD_RULES, "Sea AI", SEA_RULES, seed=4)
    players = (
        replace(state.players[0], money=opponent_money),
        replace(state.players[1], money=ai_money),
    )
    return replace(state, players=players, turn=1, phase=TurnPhase.POST_ACTION)


def test_ai_search_depth_increases_as_belief_shrinks() -> None:
    assert ai_search_depth(250_001) == 1
    assert ai_search_depth(250_000) == 2
    assert ai_search_depth(25_000) == 3


def test_ai_only_buys_extra_accusation_for_campaign_critical_win() -> None:
    knowledge = _knowledge_with_one_pair()

    ordinary_round = _ai_post_action_state(100_000, 100_000)
    assert not should_buy_extra_for_accusation(ordinary_round, knowledge)

    campaign_point = _ai_post_action_state(CAMPAIGN_TARGET, 100_000)
    assert should_buy_extra_for_accusation(campaign_point, knowledge)
