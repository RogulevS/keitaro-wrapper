const campaignSelect = document.querySelector("#campaign-id");
const fetchButton = document.querySelector("#fetch-streams");
const streamsRoot = document.querySelector("#streams");
const errorBox = document.querySelector("#editor-error");
let state = null;

function showError(message) {
  errorBox.hidden = !message;
  errorBox.textContent = message || "";
}

async function readJson(response) {
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : "Запрос не выполнен");
  }
  return payload;
}

async function loadCampaigns() {
  if (fetchButton.disabled) return;
  const response = await fetch("/api/remote-campaigns");
  const payload = await readJson(response);
  campaignSelect.replaceChildren();
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "Выберите кампанию";
  campaignSelect.append(empty);
  for (const campaign of payload) {
    const option = document.createElement("option");
    option.value = campaign.id;
    option.textContent = campaign.id + " · " + campaign.name;
    campaignSelect.append(option);
  }
  const params = new URLSearchParams(window.location.search);
  const selected = params.get("campaign");
  if (selected) {
    campaignSelect.value = selected;
    await fetchStreams();
  }
}

function offerSearch(streamId) {
  const wrap = document.createElement("div");
  wrap.className = "add-row";
  const label = document.createElement("label");
  label.textContent = "Оффер";
  const input = document.createElement("input");
  input.placeholder = "поиск по названию или id";
  input.autocomplete = "off";
  const hidden = document.createElement("input");
  hidden.type = "hidden";
  const list = document.createElement("ul");
  list.className = "suggest";
  list.hidden = true;
  label.append(input, hidden, list);
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Add";
  let timer = 0;
  input.addEventListener("input", () => {
    hidden.value = "";
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const response = await fetch("/api/offers?q=" + encodeURIComponent(input.value));
      const payload = await readJson(response);
      list.replaceChildren();
      list.hidden = payload.length === 0;
      for (const offer of payload) {
        const item = document.createElement("li");
        const pick = document.createElement("button");
        pick.type = "button";
        pick.textContent = offer.id + " · " + offer.name;
        pick.addEventListener("click", () => {
          hidden.value = offer.id;
          input.value = pick.textContent;
          list.hidden = true;
        });
        item.append(pick);
        list.append(item);
      }
    }, 200);
  });
  button.addEventListener("click", async () => {
    if (!hidden.value) {
      showError("Выберите оффер из подсказки");
      return;
    }
    await mutate("/api/streams/" + streamId + "/offers", {offer_id: Number(hidden.value)});
  });
  wrap.append(label, button);
  return wrap;
}

function render() {
  streamsRoot.replaceChildren();
  if (!state) return;
  for (const stream of state.streams) {
    const card = document.createElement("article");
    card.className = "stream" + (stream.is_dirty ? " dirty" : "");
    const header = document.createElement("header");
    const title = document.createElement("h2");
    title.textContent = stream.name;
    const meta = document.createElement("span");
    meta.className = "muted";
    if (stream.tracks_offers) {
      meta.textContent = (stream.is_dirty ? "не опубликован · " : "") + "сумма " + stream.active_share_total + "%";
    } else {
      meta.textContent = "поток без офферов";
    }
    header.append(title, meta);
    card.append(header);
    if (!stream.tracks_offers) {
      const note = document.createElement("p");
      note.className = "muted";
      note.textContent = "Содержимое этого потока не показываем: в нём нет офферов.";
      card.append(note);
      streamsRoot.append(card);
      continue;
    }
    const table = document.createElement("table");
    const head = document.createElement("tr");
    for (const name of ["ID", "Оффер", "Вес", "Pin", ""]) {
      const cell = document.createElement("th");
      cell.textContent = name;
      head.append(cell);
    }
    table.append(head);
    for (const offer of stream.offers) {
      const row = document.createElement("tr");
      if (offer.status === "removed") row.className = "removed";
      const idCell = document.createElement("td");
      idCell.textContent = offer.keitaro_offer_id;
      const nameCell = document.createElement("td");
      nameCell.textContent = offer.name;
      const shareCell = document.createElement("td");
      if (offer.pinned && offer.status === "active") {
        const input = document.createElement("input");
        input.className = "share";
        input.type = "number";
        input.min = "0";
        input.max = "100";
        input.value = offer.share;
        input.addEventListener("change", () => {
          mutate("/api/streams/" + stream.id + "/offers/" + offer.id + "/pin", {
            pinned: true,
            share: Number(input.value),
          });
        });
        shareCell.append(input, document.createTextNode("%"));
      } else {
        shareCell.textContent = offer.share + "%";
      }
      const pinCell = document.createElement("td");
      if (offer.status === "active") {
        const pin = document.createElement("input");
        pin.type = "checkbox";
        pin.checked = offer.pinned;
        pin.addEventListener("change", () => {
          mutate("/api/streams/" + stream.id + "/offers/" + offer.id + "/pin", {
            pinned: pin.checked,
            share: offer.share,
          });
        });
        pinCell.append(pin);
      }
      const actionCell = document.createElement("td");
      const action = document.createElement("button");
      action.type = "button";
      action.className = offer.status === "removed" ? "linkish bring" : "linkish";
      action.textContent = offer.status === "removed" ? "Bring back" : "Remove";
      action.addEventListener("click", () => {
        const verb = offer.status === "removed" ? "restore" : "remove";
        mutate("/api/streams/" + stream.id + "/offers/" + offer.id + "/" + verb, {});
      });
      actionCell.append(action);
      row.append(idCell, nameCell, shareCell, pinCell, actionCell);
      table.append(row);
    }
    card.append(table, offerSearch(stream.id));
    const actions = document.createElement("div");
    actions.className = "actions";
    const push = document.createElement("button");
    push.type = "button";
    push.textContent = "Push to Keitaro";
    push.disabled = !stream.is_dirty;
    push.addEventListener("click", () => mutate("/api/streams/" + stream.id + "/push", {}));
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ghost";
    cancel.textContent = "Cancel";
    cancel.disabled = !stream.is_dirty;
    cancel.addEventListener("click", () => mutate("/api/streams/" + stream.id + "/cancel", {}));
    actions.append(push, cancel);
    card.append(actions);
    streamsRoot.append(card);
  }
}

async function mutate(url, body) {
  showError("");
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    state = await readJson(response);
    render();
  } catch (error) {
    showError(error.message);
  }
}

async function fetchStreams() {
  if (!campaignSelect.value) {
    showError("Выберите кампанию");
    return;
  }
  showError("");
  try {
    const response = await fetch("/api/campaigns/" + campaignSelect.value + "/fetch", {method: "POST"});
    state = await readJson(response);
    const url = new URL(window.location.href);
    url.searchParams.set("campaign", campaignSelect.value);
    window.history.replaceState({}, "", url);
    render();
  } catch (error) {
    showError(error.message);
  }
}

fetchButton?.addEventListener("click", fetchStreams);
loadCampaigns().catch((error) => showError(error.message));
