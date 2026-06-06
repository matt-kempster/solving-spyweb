import { filterFirstAnswer, filterPaidSecondAnswer, pairCount } from "./belief.js";
export function applyObservedEvent(universe, encoding, state, event) {
    const before = state.belief;
    let after = before;
    if (event.type === "question-answered") {
        after = filterFirstAnswer(universe, before, encoding.questionId(event.question), encoding.answerCode(event.answer));
    }
    else if (event.type === "second-answer-bought") {
        after = filterPaidSecondAnswer(universe, before, encoding.questionId(event.question), encoding.answerCode(event.first), encoding.answerCode(event.second));
    }
    else if (event.type === "accusation-resolved") {
        const matches = [];
        for (const board of before) {
            const isPair = universe.ringleader[board] === event.ringleader &&
                universe.hideout[board] === event.hideout;
            if (isPair === event.correct)
                matches.push(board);
        }
        after = Uint32Array.from(matches);
    }
    const step = {
        sequence: state.trace.length + 1,
        event,
        boardsBefore: before.length,
        boardsAfter: after.length,
        pairsBefore: pairCount(universe, before),
        pairsAfter: pairCount(universe, after)
    };
    return { belief: after, trace: [...state.trace, step] };
}
