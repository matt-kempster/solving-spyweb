export const fullBelief = (universe) => Uint32Array.from({ length: universe.boardCount }, (_, index) => index);
export function pairKey(ringleader, hideout, cityCount) {
    return Number(ringleader) * cityCount + Number(hideout);
}
export function pairCount(universe, belief) {
    const pairs = new Set();
    for (const board of belief) {
        pairs.add(pairKey(universe.ringleader[board] ?? 0, universe.hideout[board] ?? 0, universe.cityCount));
    }
    return pairs.size;
}
export function filterFirstAnswer(universe, belief, question, observed) {
    const matches = [];
    const offset = question * universe.boardCount;
    const dual = universe.dualQuestion[question] === 1;
    for (const board of belief) {
        if (universe.answer0[offset + board] === observed ||
            (dual && universe.answer1[offset + board] === observed)) {
            matches.push(board);
        }
    }
    return Uint32Array.from(matches);
}
export function filterPaidSecondAnswer(universe, belief, question, first, second) {
    const matches = [];
    const offset = question * universe.boardCount;
    for (const board of belief) {
        const a0 = universe.answer0[offset + board];
        const a1 = universe.answer1[offset + board];
        if ((a0 === first && a1 === second) || (a1 === first && a0 === second))
            matches.push(board);
    }
    return Uint32Array.from(matches);
}
export function scoreQuestion(universe, belief, question) {
    const answers = new Set();
    const offset = question * universe.boardCount;
    for (const board of belief) {
        answers.add(universe.answer0[offset + board]);
        if (universe.dualQuestion[question] === 1)
            answers.add(universe.answer1[offset + board]);
    }
    const partitions = [...answers].map((answer) => {
        const boards = filterFirstAnswer(universe, belief, question, answer);
        return { answer, boards: boards.length, pairs: pairCount(universe, boards) };
    });
    return {
        question,
        worstBoards: Math.max(...partitions.map((partition) => partition.boards)),
        worstPairs: Math.max(...partitions.map((partition) => partition.pairs)),
        partitions
    };
}
export function rankQuestions(universe, belief) {
    return Array.from({ length: universe.dualQuestion.length }, (_, q) => scoreQuestion(universe, belief, q)).sort((a, b) => a.worstPairs - b.worstPairs || a.worstBoards - b.worstBoards);
}
