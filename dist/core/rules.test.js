import { describe, expect, test } from "vitest";
import { fixtureRules } from "./catalog.js";
import { answerQuestion, validateBoard } from "./rules.js";
import { cityId, spyId } from "./model.js";
const board = {
    ringleader: spyId(8),
    hideout: cityId(4),
    occupantByCity: [spyId(0), spyId(1), spyId(2), spyId(3), null, spyId(4), spyId(5), spyId(6), spyId(7)]
};
describe("rules engine", () => {
    test("validates and resolves visible, landmark, hideout, and ringleader answers", () => {
        expect(() => validateBoard(fixtureRules, board)).not.toThrow();
        expect(answerQuestion(fixtureRules, board, { spy: spyId(0), sense: "look" })).toEqual([
            { kind: "landmark", landmark: 0 }
        ]);
        expect(answerQuestion(fixtureRules, board, { spy: spyId(1), sense: "point" })).toEqual([
            { kind: "nothing" }
        ]);
        expect(answerQuestion(fixtureRules, board, { spy: spyId(8), sense: "look" })).toEqual([
            { kind: "nothing" }
        ]);
    });
});
