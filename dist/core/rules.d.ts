import { type Board, type Question, type QuestionAnswers, type Rules } from "./model.js";
export declare function validateRules(rules: Rules): void;
export declare function validateBoard(rules: Rules, board: Board): void;
export declare function answerQuestion(rules: Rules, board: Board, question: Question): QuestionAnswers;
