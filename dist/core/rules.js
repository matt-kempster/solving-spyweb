import { directionDelta } from "./model.js";
const sameCoord = (a, b) => a.row === b.row && a.col === b.col;
export function validateRules(rules) {
    if (rules.spies.length !== rules.cities.length) {
        throw new Error("Spy Web requires the same number of spies and cities");
    }
    rules.spies.forEach((spy, index) => {
        if (spy.id !== index)
            throw new Error(`Spy ids must be dense; found ${spy.id} at ${index}`);
    });
    rules.cities.forEach((city, index) => {
        if (city.id !== index)
            throw new Error(`City ids must be dense; found ${city.id} at ${index}`);
    });
}
export function validateBoard(rules, board) {
    validateRules(rules);
    if (board.occupantByCity.length !== rules.cities.length) {
        throw new Error("Board must have exactly one slot per city");
    }
    if (board.occupantByCity[board.hideout] !== null) {
        throw new Error("Hideout city must be empty");
    }
    const occupants = board.occupantByCity.filter((spy) => spy !== null);
    if (occupants.length !== rules.spies.length - 1)
        throw new Error("Board must contain every non-ringleader spy");
    if (occupants.includes(board.ringleader))
        throw new Error("Ringleader must not be on the board");
    if (new Set(occupants).size !== occupants.length)
        throw new Error("A spy may only occupy one city");
}
function answerDirection(rules, board, spy, direction) {
    if (spy === board.ringleader)
        return { kind: "nothing" };
    const cityIndex = board.occupantByCity.findIndex((occupant) => occupant === spy);
    if (cityIndex < 0)
        throw new Error(`Visible spy ${spy} has no city`);
    const start = rules.cities[cityIndex];
    if (start === undefined)
        throw new Error(`Unknown city ${cityIndex}`);
    const delta = directionDelta[direction];
    const target = { row: start.coord.row + delta.row, col: start.coord.col + delta.col };
    const landmark = rules.landmarks.find((candidate) => sameCoord(candidate.coord, target));
    if (landmark !== undefined)
        return { kind: "landmark", landmark: landmark.id };
    const targetCity = rules.cities.find((candidate) => sameCoord(candidate.coord, target));
    if (targetCity === undefined)
        return { kind: "nothing" };
    const occupant = board.occupantByCity[targetCity.id];
    return occupant === null || occupant === undefined ? { kind: "nothing" } : { kind: "spy", spy: occupant };
}
export function answerQuestion(rules, board, question) {
    const spy = rules.spies[question.spy];
    if (spy === undefined)
        throw new Error(`Unknown spy ${question.spy}`);
    const directions = spy.directions[question.sense];
    const first = answerDirection(rules, board, question.spy, directions[0]);
    return directions.length === 1
        ? [first]
        : [first, answerDirection(rules, board, question.spy, directions[1])];
}
