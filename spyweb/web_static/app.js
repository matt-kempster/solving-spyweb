let state;
const $ = (id) => document.getElementById(id);
const money = (n) => `$${n.toLocaleString()}`;

async function load() {
  const response = await fetch(`/api/state?viewer=${$("viewer").value}`);
  state = await response.json();
  render();
}

async function act(payload) {
  $("error").textContent = state.aiEnabled && payload.type === "end_turn" ? "Sea AI is choosing…" : "";
  payload.player = state.viewer;
  const response = await fetch("/api/action", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) { $("error").textContent = result.error; return; }
  state = result;
  render();
}

function directions(card) {
  const label = (items) => items.length ? items.join("/") : "–";
  return `L ${label(card.look)} · H ${label(card.hear)} · P ${label(card.point)}`;
}

function render() {
  const me = state.players[state.viewer], other = state.players[1 - state.viewer];
  $("viewer").disabled = state.aiEnabled;
  const belief = state.aiBelief === null ? "" : ` · AI knowledge: ${state.aiBelief.pairs} pairs`;
  $("status").textContent = `Round ${state.round} · Turn: ${state.players[state.turn].name} · ${me.name} ${money(me.money)} · ${other.name} ${money(other.money)}${belief}`;
  $("secret").textContent = `Ringleader: ${me.ringleader} · Hideout: ${me.hideout}`;
  $("board").innerHTML = me.board.map(cell => `<div class="cell"><strong>${cell.city}</strong>${cell.occupant}</div>`).join("");
  $("cards").innerHTML = state.opponentCards.map(card => `<div class="card"><strong>${card.name}</strong> ${money(card.bounty)}<div class="dirs">${directions(card)}</div></div>`).join("");
  renderActions();
  renderKnowledge();
  renderHistory();
  renderNotes();
}

function renderActions() {
  const active = state.viewer === state.turn;
  if (state.campaignWinner !== null) {
    $("actions").innerHTML = `<p>${state.players[state.campaignWinner].name} won the campaign.</p>`;
    return;
  }
  if (state.winner !== null) {
    $("actions").innerHTML = `<p>${state.players[state.winner].name} won the round.</p><button id="next">Start next round</button>`;
    $("next").onclick = () => act({type: "next_round"});
    return;
  }
  if (state.aiQuestion !== null) {
    $("actions").innerHTML = `<p>Sea AI asks: What does ${state.aiQuestion.spy} ${state.aiQuestion.sense}?</p>
      <p>Choose which truthful answer to reveal first:</p>
      ${state.aiQuestion.answers.map((answer, i) => `<button class="ai-answer" data-index="${i}">${answer}</button>`).join("")}`;
    document.querySelectorAll(".ai-answer").forEach(button => button.onclick = () => act({type: "ai_answer", firstAnswerIndex: Number(button.dataset.index)}));
    return;
  }
  if (!active) { $("actions").innerHTML = "<p>Switch to the current player to act.</p>"; return; }
  if (state.phase === "dual_second_answer") {
    $("actions").innerHTML = `<button id="buy-second">Pay $100k for second answer</button><button id="decline-second">Decline</button>`;
    $("buy-second").onclick = () => act({type: "buy_second"});
    $("decline-second").onclick = () => act({type: "decline_second"});
    return;
  }
  if (state.phase === "post_action") {
    $("actions").innerHTML = `<button id="buy-extra" ${state.extraActionBought ? "disabled" : ""}>Pay $100k for another action</button><button id="end">End turn</button>`;
    $("buy-extra").onclick = () => act({type: "buy_extra"});
    $("end").onclick = () => act({type: "end_turn"});
    return;
  }
  const options = state.questions.map((q, i) => `<option value="${i}">${q.spyName} ${q.sense}${q.dual ? " (choose direction)" : ""}</option>`).join("");
  const suspects = state.opponentCards.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
  const cities = state.cities.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
  $("actions").innerHTML = `
    <select id="question">${options}</select><span id="direction-choice"><select id="first"><option value="0">first direction</option><option value="1">second direction</option></select></span><button id="ask">Ask</button>
    <br><select id="suspect">${suspects}</select><select id="city">${cities}</select><button id="accuse">Accuse</button>`;
  const updateDirectionChoice = () => {
    const q = state.questions[Number($("question").value)];
    $("direction-choice").hidden = !q.dual || state.aiEnabled;
  };
  $("question").onchange = updateDirectionChoice;
  updateDirectionChoice();
  $("ask").onclick = () => {
    const q = state.questions[Number($("question").value)];
    act({type: "ask", spy: q.spy, sense: q.sense, firstAnswerIndex: q.dual && !state.aiEnabled ? Number($("first").value) : 0});
  };
  $("accuse").onclick = () => act({type: "accuse", ringleader: Number($("suspect").value), hideout: Number($("city").value)});
}

function renderKnowledge() {
  $("knowledge").innerHTML = state.players.map((p, i) => `<div class="knowledge"><strong>${p.name}</strong><ul>${(state.knowledge[i].length ? state.knowledge[i] : ["No observations yet."]).map(x => `<li>${x}</li>`).join("")}</ul></div>`).join("");
}

function renderHistory() {
  $("history").innerHTML = state.history.map(e => `<li>${state.players[e.player].name}: ${e.text}</li>`).join("");
}

function notesKey() { return `spyweb-notes-${state.viewer}-${state.players[1-state.viewer].faction}`; }
function savedNotes() { return JSON.parse(localStorage.getItem(notesKey()) || "{}"); }
function saveNotes(notes) { localStorage.setItem(notesKey(), JSON.stringify(notes)); }

function renderNotes() {
  const notes = savedNotes();
  const items = [...state.opponentCards.map(c => ({id: `spy-${c.id}`, name: c.name, dirs: directions(c)})), {id: "hideout", name: "HIDEOUT", dirs: ""}];
  const noteHtml = item => `<div class="note" draggable="true" data-note="${item.id}"><strong>${item.name}</strong><div class="dirs">${item.dirs}</div></div>`;
  $("notes-pool").innerHTML = items.filter(x => !notes[x.id]).map(noteHtml).join("");
  $("notes-grid").innerHTML = state.cities.map(city => `<div class="cell dropzone" data-city="${city.id}"><strong>${city.name}</strong>${items.filter(x => notes[x.id] === String(city.id)).map(noteHtml).join("")}</div>`).join("");
  document.querySelectorAll(".note").forEach(el => el.addEventListener("dragstart", ev => ev.dataTransfer.setData("text/plain", el.dataset.note)));
  document.querySelectorAll(".dropzone").forEach(zone => {
    zone.addEventListener("dragover", ev => ev.preventDefault());
    zone.addEventListener("drop", ev => {
      ev.preventDefault();
      const n = savedNotes(), id = ev.dataTransfer.getData("text/plain");
      if (zone.dataset.city === undefined) delete n[id]; else n[id] = zone.dataset.city;
      saveNotes(n); renderNotes();
    });
  });
}

$("viewer").addEventListener("change", load);
$("clear-notes").addEventListener("click", () => { localStorage.removeItem(notesKey()); renderNotes(); });
load();
