import { createInterface } from "node:readline/promises";
import { stdin, stdout } from "node:process";
import { fixtureRules } from "../core/catalog.js";
import type { Answer, Sense } from "../core/model.js";
import { createEncoding } from "../solver/encoding.js";
import { fullBelief, pairCount, rankQuestions } from "../solver/belief.js";
import { applyObservedEvent, type ReplayState } from "../solver/replay.js";
import { buildUniverse } from "../solver/universe.js";

const encoding = createEncoding(fixtureRules);
const sampleLimit = Number.parseInt(process.env["SPYWEB_BOARD_LIMIT"] ?? "50000", 10);
stdout.write(`Building a ${sampleLimit.toLocaleString()}-board development universe...\n`);
const universe = buildUniverse(fixtureRules, encoding, sampleLimit);
let state: ReplayState = { belief: fullBelief(universe), trace: [] };

function answerLabel(answer: Answer): string {
  if (answer.kind === "nothing") return "Nothing";
  return answer.kind === "spy"
    ? (fixtureRules.spies[answer.spy]?.name ?? `Spy ${answer.spy}`)
    : (fixtureRules.landmarks[answer.landmark]?.name ?? `Landmark ${answer.landmark}`);
}

function showStatus(): void {
  stdout.write(`\nPossible boards: ${state.belief.length.toLocaleString()}\n`);
  stdout.write(`Possible ringleader/hideout pairs: ${pairCount(universe, state.belief)}\n`);
  for (const score of rankQuestions(universe, state.belief).slice(0, 5)) {
    const question = encoding.decodeQuestion(score.question);
    const spy = fixtureRules.spies[question.spy];
    stdout.write(
      `  ${spy?.name ?? question.spy} ${question.sense}: worst ${score.worstPairs} pairs / ${score.worstBoards.toLocaleString()} boards\n`
    );
  }
}

function parseAnswer(raw: string): Answer {
  const normalized = raw.trim().toLowerCase();
  if (normalized === "nothing") return { kind: "nothing" };
  const spy = fixtureRules.spies.find((candidate) => candidate.name.toLowerCase() === normalized);
  if (spy !== undefined) return { kind: "spy", spy: spy.id };
  const landmark = fixtureRules.landmarks.find((candidate) => candidate.name.toLowerCase() === normalized);
  if (landmark !== undefined) return { kind: "landmark", landmark: landmark.id };
  throw new Error(`Unknown answer: ${raw}`);
}

async function main(): Promise<void> {
  const rl = createInterface({ input: stdin, output: stdout });
  try {
    while (true) {
      showStatus();
      const command = (await rl.question("\n[a]dd observation, [t]race, [q]uit: ")).trim().toLowerCase();
      if (command === "q") break;
      if (command === "t") {
        for (const step of state.trace) {
          stdout.write(
            `${step.sequence}. ${step.event.type}: ${step.boardsBefore} -> ${step.boardsAfter} boards, ${step.pairsBefore} -> ${step.pairsAfter} pairs\n`
          );
        }
        continue;
      }
      if (command !== "a") continue;
      const spyName = (await rl.question("Spy: ")).trim().toLowerCase();
      const spy = fixtureRules.spies.find((candidate) => candidate.name.toLowerCase() === spyName);
      if (spy === undefined) throw new Error(`Unknown spy: ${spyName}`);
      const sense = (await rl.question("Sense (look/hear/point): ")).trim().toLowerCase() as Sense;
      if (!["look", "hear", "point"].includes(sense)) throw new Error(`Unknown sense: ${sense}`);
      const answer = parseAnswer(await rl.question("Answer (spy, landmark, or Nothing): "));
      state = applyObservedEvent(universe, encoding, state, {
        type: "question-answered",
        asker: "bird",
        question: { spy: spy.id, sense },
        answer
      });
      stdout.write(`Recorded ${spy.name} ${sense} = ${answerLabel(answer)}\n`);
    }
  } finally {
    rl.close();
  }
}

void main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`Spy Web TUI failed: ${message}\n`);
  process.exitCode = 1;
});
