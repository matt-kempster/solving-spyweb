import {
  answerCode,
  landmarkId,
  questionId,
  senses,
  spyId,
  type Answer,
  type AnswerCode,
  type Question,
  type QuestionId,
  type Rules
} from "../core/model.js";

export interface Encoding {
  readonly nothing: AnswerCode;
  readonly questionCount: number;
  questionId(question: Question): QuestionId;
  decodeQuestion(id: QuestionId): Question;
  answerCode(answer: Answer): AnswerCode;
  decodeAnswer(code: AnswerCode): Answer;
}

export function createEncoding(rules: Rules): Encoding {
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
      if (sense === undefined) throw new Error(`Invalid question id ${id}`);
      return { spy: spy as Question["spy"], sense };
    },
    answerCode: (answer) => {
      if (answer.kind === "nothing") return nothing;
      return answer.kind === "spy"
        ? answerCode(answer.spy)
        : answerCode(landmarkOffset + answer.landmark);
    },
    decodeAnswer: (code) => {
      if (code === nothing) return { kind: "nothing" };
      if (code < landmarkOffset) return { kind: "spy", spy: spyId(code) };
      return {
        kind: "landmark",
        landmark: landmarkId(code - landmarkOffset)
      };
    }
  };
}
