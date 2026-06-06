import { describe, expect, test } from "vitest";
import { fixtureRules } from "../core/catalog.js";
import { spyId } from "../core/model.js";
import { fullBelief, pairCount, rankQuestions } from "./belief.js";
import { createEncoding } from "./encoding.js";
import { applyObservedEvent } from "./replay.js";
import { buildUniverse } from "./universe.js";
describe("solver translation and replay", () => {
    test("scores questions and deterministically replays an observation", () => {
        const encoding = createEncoding(fixtureRules);
        const universe = buildUniverse(fixtureRules, encoding, 2_000);
        const belief = fullBelief(universe);
        const ranking = rankQuestions(universe, belief);
        expect(ranking).toHaveLength(27);
        expect(pairCount(universe, belief)).toBe(81);
        const landmark = fixtureRules.landmarks[0];
        if (landmark === undefined)
            throw new Error("Fixture landmark missing");
        const event = {
            type: "question-answered",
            asker: "bird",
            question: { spy: spyId(0), sense: "look" },
            answer: { kind: "landmark", landmark: landmark.id }
        };
        const next = applyObservedEvent(universe, encoding, { belief, trace: [] }, event);
        expect(next.belief.length).toBeLessThan(belief.length);
        expect(next.trace[0]).toMatchObject({
            boardsBefore: belief.length,
            boardsAfter: next.belief.length,
            pairsBefore: pairCount(universe, belief),
            pairsAfter: pairCount(universe, next.belief)
        });
    });
});
