import { type Answer, type AnswerCode, type Question, type QuestionId, type Rules } from "../core/model.js";
export interface Encoding {
    readonly nothing: AnswerCode;
    readonly questionCount: number;
    questionId(question: Question): QuestionId;
    decodeQuestion(id: QuestionId): Question;
    answerCode(answer: Answer): AnswerCode;
    decodeAnswer(code: AnswerCode): Answer;
}
export declare function createEncoding(rules: Rules): Encoding;
