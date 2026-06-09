let state;
let artManifest;
const $ = (id) => document.getElementById(id);
const money = (n) => `$${n.toLocaleString()}`;
const AI_KNOWLEDGE_KEY = "spyweb-show-ai-knowledge";
const THEME_KEY = "spyweb-theme";
const COMPONENT_COUNT = 9;
const setupLayouts = {};
const accusationSelection = {spy: null, city: null};
let showingRevealedBoard = false;
const transparentDragImage = new Image();
transparentDragImage.src = "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";

function beginDrag(event, value, element) {
  event.dataTransfer.setData("text/plain", value);
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setDragImage(transparentDragImage, 0, 0);
  element.classList.add("dragging");
}

function showAiKnowledge() {
  return localStorage.getItem(AI_KNOWLEDGE_KEY) === "true";
}

async function load() {
  if (artManifest === undefined) await loadArtManifest();
  const response = await fetch(`/api/state?viewer=${$("viewer").value}`);
  state = await response.json();
  render();
}

async function loadArtManifest() {
  const response = await fetch("/local_art/manifest.json");
  artManifest = response.ok ? await response.json() : null;
}

async function act(payload) {
  const resetsSetup = payload.type === "choose_faction" || payload.type === "new_game";
  if (["choose_faction", "new_game", "next_round"].includes(payload.type)) showingRevealedBoard = false;
  if (payload.type === "new_game") clearLocalAnnotations();
  if (payload.type === "choose_faction" || payload.type === "new_game") {
    $("error").textContent = `Starting a new ${payload.faction || state.players[state.humanPlayer].faction} game…`;
  } else {
    $("error").textContent = state.aiEnabled && payload.type === "end_turn" ? "AI is choosing…" : "";
  }
  payload.player = state.viewer;
  const response = await fetch("/api/action", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) { $("error").textContent = result.error; return; }
  state = result;
  if (["choose_faction", "new_game", "next_round", "accuse"].includes(payload.type)) clearAccusationSelection();
  if (resetsSetup) clearSetupLayouts();
  $("error").textContent = "";
  render();
}

const arrow = {N: "↑", NE: "↗", E: "→", SE: "↘", S: "↓", SW: "↙", W: "←", NW: "↖"};

function cardImage(card) {
  return artManifest?.cards?.[card.faction]?.[card.name] || null;
}

function cardHtml(card, options = {}) {
  if (card.hideout || card.landmark) {
    const drag = options.draggable ? `draggable="true" data-note="${card.noteId}"` : "";
    const mark = options.markKey ? `data-mark-key="${options.markKey}"` : "";
    const marked = options.markKey && savedMarks()[options.markKey] ? "marked" : "";
    const accuseCity = options.accuseCity !== undefined ? `data-accuse-city="${options.accuseCity}"` : "";
    const accused = options.accuseCity !== undefined && accusationSelection.city === Number(options.accuseCity) ? "accused" : "";
    return `<div class="spy-card hideout ${options.draggable ? "draggable" : ""} ${marked} ${accused}" ${drag} ${mark} ${accuseCity}><strong>${card.landmark || "HIDEOUT"}</strong></div>`;
  }
  const image = cardImage(card);
  const edges = {};
  for (const [sense, short] of [["look", "L"], ["hear", "H"], ["point", "P"]]) {
    for (const dir of card[sense]) {
      (edges[dir] ||= []).push(`<span class="sense ${sense}" title="${sense} ${dir}">${short}${arrow[dir]}</span>`);
    }
  }
  const markers = Object.entries(edges).map(([dir, values]) => `<span class="edge ${dir.toLowerCase()}">${values.join("")}</span>`).join("");
  const drag = options.draggable ? `draggable="true" data-note="${card.noteId}"` : "";
  const art = image ? `<img class="card-art" src="${image}" alt="">` : "";
  const opponent = options.opponent ? `data-opponent-spy="${card.id}"` : "";
  const mark = options.markKey ? `data-mark-key="${options.markKey}"` : "";
  const marked = options.markKey && savedMarks()[options.markKey] ? "marked" : "";
  const accused = options.opponent && accusationSelection.spy === card.id ? "accused" : "";
  return `<div class="spy-card ${image ? "with-art" : ""} ${options.draggable ? "draggable" : ""} ${marked} ${accused}" ${drag} ${opponent} ${mark}>${art}${markers}<strong>${card.name}</strong><div class="muted">${money(card.bounty)}</div></div>`;
}

function closeQuestionMenu() {
  $("question-menu").hidden = true;
}

function askQuestion(question, firstAnswerIndex = 0) {
  closeQuestionMenu();
  act({type: "ask", spy: question.spy, sense: question.sense, firstAnswerIndex});
}

function selectAccusedSpy(spyId) {
  accusationSelection.spy = spyId;
  closeQuestionMenu();
  render();
}

function selectAccusedCity(cityId) {
  accusationSelection.city = cityId;
  closeQuestionMenu();
  render();
}

function clearAccusationSelection() {
  accusationSelection.spy = null;
  accusationSelection.city = null;
}

function openQuestionMenu(event, spyId) {
  event.preventDefault();
  const active = state.viewer === state.turn && state.phase === "action" && state.setupComplete && state.winner === null;
  const questions = state.questions.filter(question => question.spy === spyId);
  if (!active) return;
  const buttons = questions.flatMap(question => {
    if (question.dual && !state.aiEnabled) {
      return [0, 1].map(index => `<button data-spy="${question.spy}" data-sense="${question.sense}" data-first="${index}">${question.sense} · direction ${index + 1}</button>`);
    }
    return [`<button data-spy="${question.spy}" data-sense="${question.sense}" data-first="0">${question.sense}</button>`];
  }).join("");
  const menu = $("question-menu");
  const card = state.opponentCards.find(item => item.id === spyId);
  menu.innerHTML = `<strong>${card.name}</strong>${buttons}<button class="danger" data-accuse-spy="${spyId}">Accuse this spy</button>`;
  menu.hidden = false;
  menu.style.left = `${Math.min(event.clientX, window.innerWidth - 190)}px`;
  menu.style.top = `${Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8)}px`;
  menu.querySelectorAll("button[data-sense]").forEach(button => {
    button.onclick = () => {
      const question = state.questions.find(item => item.spy === Number(button.dataset.spy) && item.sense === button.dataset.sense);
      if (question) askQuestion(question, Number(button.dataset.first));
    };
  });
  menu.querySelector("[data-accuse-spy]").onclick = () => selectAccusedSpy(spyId);
}

function clearSetupLayouts() {
  for (const key of Object.keys(setupLayouts)) delete setupLayouts[key];
}

function setupKey() {
  const me = state.players[state.viewer];
  const generatedLayout = me.board.map(cell => cell.occupant).join(",");
  return `${state.round}-${state.viewer}-${me.faction}-${me.ringleader}-${generatedLayout}`;
}

function setupLayout() {
  const key = setupKey();
  if (!setupLayouts[key]) setupLayouts[key] = state.players[state.viewer].board.map(cell => cell.occupant);
  return setupLayouts[key];
}

function shuffleSetupLayout() {
  const layout = setupLayout();
  for (let index = layout.length - 1; index > 0; index--) {
    const other = Math.floor(Math.random() * (index + 1));
    [layout[index], layout[other]] = [layout[other], layout[index]];
  }
}

function renderPrivateBoard(me, ownByName) {
  if (!state.setupEnabled || state.setupReady[state.viewer]) {
    $("board").innerHTML = me.board.map(cell => `<div class="cell"><strong>${cell.city}</strong>${cell.occupant === "HIDEOUT" ? cardHtml({hideout: true}, {markKey: "own-hideout"}) : cardHtml(ownByName[cell.occupant], {markKey: `own-${ownByName[cell.occupant].id}`})}</div>`).join("");
    return;
  }
  const layout = setupLayout();
  $("board").innerHTML = me.board.map((cell, city) => {
    const occupant = layout[city];
    const card = occupant === "HIDEOUT" ? cardHtml({hideout: true}, {markKey: "own-hideout"}) : cardHtml(ownByName[occupant], {markKey: `own-${ownByName[occupant].id}`});
    return `<div class="cell setup-cell" data-setup-city="${city}"><strong>${cell.city}</strong><div class="setup-card" draggable="true" data-setup-city="${city}">${card}</div></div>`;
  }).join("");
  document.querySelectorAll(".setup-card").forEach(card => {
    card.addEventListener("dragstart", event => beginDrag(event, card.dataset.setupCity, card));
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
  });
  document.querySelectorAll(".setup-cell").forEach(cell => {
    cell.addEventListener("dragenter", () => cell.classList.add("drag-over"));
    cell.addEventListener("dragleave", () => cell.classList.remove("drag-over"));
    cell.addEventListener("dragover", event => event.preventDefault());
    cell.addEventListener("drop", event => {
      event.preventDefault();
      cell.classList.remove("drag-over");
      const source = Number(event.dataTransfer.getData("text/plain")), target = Number(cell.dataset.setupCity);
      [layout[source], layout[target]] = [layout[target], layout[source]];
      render();
    });
  });
}

function render() {
  const me = state.players[state.viewer], other = state.players[1 - state.viewer];
  $("viewer").value = String(state.viewer);
  $("viewer").disabled = state.aiEnabled;
  $("faction-control").hidden = !state.aiEnabled;
  $("ai-strategy-control").hidden = !state.aiEnabled;
  $("ai-strategy").value = state.aiStrategy;
  $("new-game").hidden = false;
  $("human-faction").value = state.players[state.humanPlayer].faction;
  $("ai-knowledge-control").hidden = !state.aiEnabled;
  $("show-ai-knowledge").checked = showAiKnowledge();
  const belief = state.aiBelief === null || !showAiKnowledge() ? "" : ` · AI knowledge: ${state.aiBelief.pairs} pairs · depth ${state.aiBelief.depth}`;
  $("status").textContent = `Round ${state.round} · Turn: ${state.players[state.turn].name} · ${me.name} ${money(me.money)} · ${other.name} ${money(other.money)}${belief}`;
  const ownByName = Object.fromEntries(state.ownCards.map(card => [card.name, card]));
  const choosingLayout = state.setupEnabled && !state.setupReady[state.viewer];
  $("secret").innerHTML = `<p>Ringleader: ${me.ringleader}${choosingLayout ? "" : ` · Hideout: ${me.hideout}`}</p>${cardHtml(ownByName[me.ringleader], {markKey: `own-${ownByName[me.ringleader].id}`})}`;
  renderPrivateBoard(me, ownByName);
  renderActions();
  renderKnowledge();
  renderDeductions();
  renderHistory();
  renderResponse();
  renderNotes();
}

function renderActions() {
  const active = state.viewer === state.turn;
  if (state.setupEnabled && !state.setupComplete) {
    if (state.setupReady[state.viewer]) {
      $("actions").innerHTML = "<p>Your layout is locked. Waiting for the other player.</p>";
    } else {
      $("actions").innerHTML = `<p>Arrange your eight visible spies and hideout, then lock the layout.</p><button id="shuffle-layout">Shuffle</button><button id="lock-layout">Lock layout</button>`;
      $("shuffle-layout").onclick = () => {
        shuffleSetupLayout();
        render();
      };
      $("lock-layout").onclick = () => {
        const ids = Object.fromEntries(state.ownCards.map(card => [card.name, card.id]));
        act({type: "set_layout", occupants: setupLayout().map(occupant => occupant === "HIDEOUT" ? -1 : ids[occupant])});
      };
    }
    return;
  }
  if (state.campaignWinner !== null) {
    $("actions").innerHTML = `<p>${state.players[state.campaignWinner].name} won the campaign.</p>`;
    return;
  }
  if (state.winner !== null) {
    $("actions").innerHTML = `<p>${state.players[state.winner].name} won the round.</p>${roundRevealHtml()}<button id="next">Start next round</button>`;
    $("next").onclick = () => act({type: "next_round"});
    return;
  }
  if (state.aiQuestion !== null) {
    $("actions").innerHTML = `<p>${state.players[state.aiPlayer].name} asks: What does ${state.aiQuestion.spy} ${state.aiQuestion.sense}?</p>
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
  const selectedSpy = state.opponentCards.find(card => card.id === accusationSelection.spy);
  const selectedCity = state.cities.find(city => city.id === accusationSelection.city);
  const disabled = selectedSpy && selectedCity ? "" : "disabled";
  $("actions").innerHTML = `
    <p>Right-click an opponent card to ask, or choose that spy for an accusation.</p>
    <p>Right-click a city name, or the hideout card while it sits on a city, to choose the hideout.</p>
    <div class="accuse-selection">
      <span>Spy: <strong>${selectedSpy ? selectedSpy.name : "none"}</strong></span>
      <span>City: <strong>${selectedCity ? selectedCity.name : "none"}</strong></span>
    </div>
    <button id="accuse" ${disabled}>Accuse</button>`;
  $("accuse").onclick = () => {
    if (accusationSelection.spy !== null && accusationSelection.city !== null) {
      act({type: "accuse", ringleader: accusationSelection.spy, hideout: accusationSelection.city});
    }
  };
}

function roundRevealHtml() {
  if (!state.roundReveal) return "";
  const rows = state.roundReveal.map(item => {
    const player = state.players[item.player];
    return `<li><strong>${player.name}</strong>: ${item.ringleader} in ${item.hideout}</li>`;
  }).join("");
  return `<div class="round-reveal"><strong>Final answers</strong><ul>${rows}</ul></div>`;
}

function renderKnowledge() {
  $("knowledge").innerHTML = state.players.map((p, i) => {
    if (state.aiEnabled && i === state.aiPlayer && !showAiKnowledge()) {
      return `<div class="knowledge hidden-knowledge"><strong>${p.name}</strong><p class="muted">Hidden. Enable “Show AI knowledge” to inspect it.</p></div>`;
    }
    return `<div class="knowledge"><strong>${p.name}</strong><ul>${(state.knowledge[i].length ? state.knowledge[i] : ["No observations yet."]).map(x => `<li>${x}</li>`).join("")}</ul></div>`;
  }).join("");
}

function sensePill(item) {
  const label = item.sense[0].toUpperCase();
  const stateClass = item.available ? (item.count > 0 ? "asked" : "unasked") : "unavailable";
  const title = item.available ? `${item.sense}: ${item.count} asked` : `${item.sense}: unavailable`;
  return `<span class="asked-sense ${stateClass}" title="${title}">${label}${item.count ? item.count : ""}</span>`;
}

function directionText(directions) {
  return directions.map(direction => arrow[direction] || direction).join("/");
}

function deductionLine(item, target) {
  return `<li><strong>${item.spy}</strong> ${item.sense} <span class="dir-text">${directionText(item.directions)}</span> → ${target}</li>`;
}

function renderOneDeduction(deduction, playerIndex) {
  if (state.aiEnabled && playerIndex === state.aiPlayer && !showAiKnowledge()) {
    return `<div class="deduction hidden-knowledge"><strong>${state.players[playerIndex].name}</strong><p class="muted">AI deductions hidden.</p></div>`;
  }
  const asked = deduction.asked.map(spy => `<div class="asked-row"><span>${spy.spy}</span><span>${spy.senses.map(sensePill).join("")}</span></div>`).join("");
  const edges = deduction.edges.length ? deduction.edges.map(item => deductionLine(item, `<strong>${item.target}</strong>`)).join("") : `<li class="muted">No spy-to-spy edges yet.</li>`;
  const anchors = deduction.anchors.length ? deduction.anchors.map(item => deductionLine(item, `<strong>${item.target}</strong>`)).join("") : `<li class="muted">No landmark anchors yet.</li>`;
  const nothings = deduction.nothings.length ? deduction.nothings.map(item => `<li><strong>${item.spy}</strong> ${item.sense} <span class="dir-text">${directionText(item.directions)}</span> → nothing</li>`).join("") : `<li class="muted">No nothing observations yet.</li>`;
  const accusations = deduction.accusations.length ? `<h4>Accusations</h4><ul>${deduction.accusations.map(item => `<li>${item.ringleader} in ${item.hideout}: ${item.correct ? "correct" : "wrong"}</li>`).join("")}</ul>` : "";
  return `<div class="deduction">
    <strong>${state.players[playerIndex].name} solving ${deduction.targetFaction}</strong>
    <div class="asked-grid">${asked}</div>
    <h4>Edges</h4><ul>${edges}</ul>
    <h4>Landmarks</h4><ul>${anchors}</ul>
    <h4>Nothing</h4><ul>${nothings}</ul>
    ${accusations}
  </div>`;
}

function renderDeductions() {
  $("deductions").innerHTML = state.deductions.map((deduction, i) => renderOneDeduction(deduction, i)).join("");
}

function renderHistory() {
  $("history").innerHTML = state.history
    .filter(e => e.kind !== "turn")
    .map(e => `<li>${state.players[e.player].name}: ${e.text}</li>`)
    .join("");
}

function renderResponse() {
  const latest = [...state.history].reverse().find(event => event.kind === "observation");
  $("response").textContent = latest ? `${state.players[latest.player].name}: ${latest.text}` : "No response yet.";
}

function notesKey() { return `spyweb-notes-${state.viewer}-${state.players[1-state.viewer].faction}`; }
function marksKey() { return `spyweb-marks-${state.viewer}-${state.players[1-state.viewer].faction}`; }
function savedNotes() { return JSON.parse(localStorage.getItem(notesKey()) || "{}"); }
function saveNotes(notes) { localStorage.setItem(notesKey(), JSON.stringify(notes)); }
function savedMarks() { return JSON.parse(localStorage.getItem(marksKey()) || "{}"); }
function saveMarks(marks) { localStorage.setItem(marksKey(), JSON.stringify(marks)); }
function clearLocalAnnotations() {
  localStorage.removeItem(notesKey());
  localStorage.removeItem(marksKey());
}

function bindCardMarks() {
  document.querySelectorAll("[data-mark-key]").forEach(card => {
    card.addEventListener("click", event => {
      if (event.button !== 0) return;
      const marks = savedMarks(), key = card.dataset.markKey;
      if (marks[key]) delete marks[key]; else marks[key] = true;
      saveMarks(marks);
      document.querySelectorAll(`[data-mark-key="${key}"]`).forEach(match => match.classList.toggle("marked", Boolean(marks[key])));
    });
  });
}

function renderNotes() {
  const canReveal = state.winner !== null && state.roundReveal !== null;
  const toggle = $("toggle-board-reveal");
  toggle.hidden = !canReveal;
  toggle.textContent = showingRevealedBoard ? "Back to notes" : "Reveal board";
  $("notes-workspace").hidden = showingRevealedBoard;
  $("notes-help").hidden = showingRevealedBoard;
  $("revealed-board").hidden = !showingRevealedBoard;
  if (showingRevealedBoard) {
    renderRevealedBoard();
    return;
  }

  const notes = savedNotes();
  const items = [
    ...state.opponentCards.map(c => ({...c, noteId: `spy-${c.id}`})),
    {noteId: "hideout", hideout: true}
  ];
  const noteOptions = (item, location = undefined) => ({
    draggable: true,
    opponent: !item.hideout,
    markKey: item.hideout ? "opp-hideout" : `opp-${item.id}`,
    accuseCity: item.hideout && location !== undefined && !String(location).startsWith("component-") ? Number(location) : undefined,
  });
  $("notes-pool").innerHTML = `<div class="legend"><span class="sense look">L look</span><span class="sense hear">H hear</span><span class="sense point">P point</span></div>${items.filter(x => !notes[x.noteId]).map(item => cardHtml(item, noteOptions(item))).join("")}`;
  const landmarks = state.landmarks.map(item => `<div class="landmark landmark-${item.name.toLowerCase()}">${item.name}</div>`).join("");
  const cities = state.cities.map(city => {
    const accusedLocation = accusationSelection.city === city.id ? "accused-location" : "";
    return `<div class="cell dropzone" data-city="${city.id}"><strong class="accuse-city-target ${accusedLocation}" data-accuse-city="${city.id}">${city.name}</strong>${items.filter(x => notes[x.noteId] === String(city.id)).map(item => cardHtml(item, noteOptions(item, city.id))).join("")}</div>`;
  }).join("");
  $("notes-grid").innerHTML = landmarks + cities;
  $("component-grid").innerHTML = Array.from({length: COMPONENT_COUNT}, (_, index) => {
    const location = `component-${index}`;
    return `<div class="cell component-bin dropzone" data-location="${location}">${items.filter(x => notes[x.noteId] === location).map(item => cardHtml(item, noteOptions(item, location))).join("")}</div>`;
  }).join("");
  document.querySelectorAll("[data-opponent-spy]").forEach(card => card.addEventListener("contextmenu", event => openQuestionMenu(event, Number(card.dataset.opponentSpy))));
  document.querySelectorAll("[data-accuse-city]").forEach(target => {
    target.addEventListener("contextmenu", event => {
      event.preventDefault();
      selectAccusedCity(Number(target.dataset.accuseCity));
    });
  });
  document.querySelectorAll(".draggable").forEach(el => {
    el.addEventListener("dragstart", event => beginDrag(event, el.dataset.note, el));
    el.addEventListener("dragend", () => el.classList.remove("dragging"));
  });
  document.querySelectorAll(".dropzone").forEach(zone => {
    zone.addEventListener("dragenter", () => zone.classList.add("drag-over"));
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("dragover", ev => {
      ev.preventDefault();
      ev.dataTransfer.dropEffect = "move";
    });
    zone.addEventListener("drop", ev => {
      ev.preventDefault();
      zone.classList.remove("drag-over");
      const n = savedNotes(), id = ev.dataTransfer.getData("text/plain");
      const location = zone.dataset.location ?? zone.dataset.city;
      if (location === undefined) delete n[id]; else n[id] = location;
      saveNotes(n); renderNotes();
    });
  });
  bindCardMarks();
}

function renderRevealedBoard() {
  const opponent = 1 - state.viewer;
  const reveal = state.roundReveal.find(item => item.player === opponent);
  const cardsByName = Object.fromEntries(state.opponentCards.map(card => [card.name, card]));
  const ringleader = cardsByName[reveal.ringleader];
  const board = reveal.board.map(cell => {
    const card = cell.occupant === "HIDEOUT" ? cardHtml({hideout: true}) : cardHtml(cardsByName[cell.occupant]);
    return `<div class="cell"><strong>${cell.city}</strong>${card}</div>`;
  }).join("");
  $("revealed-board").innerHTML = `
    <div class="revealed-secret"><strong>Ringleader: ${reveal.ringleader}</strong>${cardHtml(ringleader)}</div>
    <div class="grid">${board}</div>`;
}

$("viewer").addEventListener("change", load);
$("human-faction").addEventListener("change", () => act({type: "choose_faction", faction: $("human-faction").value}));
$("ai-strategy").addEventListener("change", () => act({type: "set_ai_strategy", strategy: $("ai-strategy").value}));
$("new-game").addEventListener("click", () => act({type: "new_game"}));
$("theme").value = localStorage.getItem(THEME_KEY) || "dark";
document.documentElement.dataset.theme = $("theme").value;
$("theme").addEventListener("change", () => {
  localStorage.setItem(THEME_KEY, $("theme").value);
  document.documentElement.dataset.theme = $("theme").value;
});
$("show-ai-knowledge").addEventListener("change", () => {
  localStorage.setItem(AI_KNOWLEDGE_KEY, $("show-ai-knowledge").checked);
  render();
});
$("toggle-board-reveal").addEventListener("click", () => {
  showingRevealedBoard = !showingRevealedBoard;
  renderNotes();
});
$("clear-notes").addEventListener("click", () => { localStorage.removeItem(notesKey()); renderNotes(); });
document.addEventListener("click", event => {
  if (!$("question-menu").contains(event.target)) closeQuestionMenu();
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") closeQuestionMenu();
});
load();
