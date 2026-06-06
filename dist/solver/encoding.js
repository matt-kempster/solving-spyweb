import { answerCode, landmarkId, questionId, senses, spyId } from "../core/model.js";
export function createEncoding(rules) {
    const spyAnswerCount = rules.spies.length;
    const landmarkOffset = spyAnswerCount;
    const nothing = answerCode(spyAnswerCount + rules.landmarks.length);
    return {
        nothing,
        questionCount: rules.spies.length * senses.length,
        questionId: ({ spy, sense }) => questionId(spy * senses.length + senses.indexOf(sense)),
        decodeQuestion: (id) => {
            const spy = Math.floor(id / senses.length);
            const sense = senses[id % senses.length];
            if (sense === undefined)
                throw new Error(`Invalid question id ${id}`);
            return { spy: spy, sense };
        },
        answerCode: (answer) => {
            if (answer.kind === "nothing")
                return nothing;
            return answer.kind === "spy"
                ? answerCode(answer.spy)
                : answerCode(landmarkOffset + answer.landmark);
        },
        decodeAnswer: (code) => {
            if (code === nothing)
                return { kind: "nothing" };
            if (code < landmarkOffset)
                return { kind: "spy", spy: spyId(code) };
            return {
                kind: "landmark",
                landmark: landmarkId(code - landmarkOffset)
            };
        }
    };
}
