const form = document.querySelector("#create-form");
const errorBox = document.querySelector("#create-error");
const resultBox = document.querySelector("#create-result");
const offerSearch = document.querySelector("#offer-search");
const offerId = document.querySelector("#offer-id");
const offerList = document.querySelector("#offer-list");

function showError(message) {
  errorBox.hidden = !message;
  errorBox.textContent = message || "";
}

function fillSelect(select, items, selected) {
  select.replaceChildren();
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name || String(item.id);
    if (String(item.id) === String(selected)) option.selected = true;
    select.append(option);
  }
}

async function loadMeta() {
  if (form.querySelector("button").disabled) return;
  const response = await fetch("/api/meta");
  const payload = await response.json();
  if (!response.ok) {
    showError(payload.detail || "Не удалось прочитать домены, группы и источники");
    return;
  }
  fillSelect(document.querySelector("#domain-id"), payload.domains, payload.selected.domain_id);
  fillSelect(document.querySelector("#group-id"), payload.groups, payload.selected.group_id);
  fillSelect(document.querySelector("#source-id"), payload.sources, payload.selected.source_id);
}

let timer = 0;
offerSearch?.addEventListener("input", () => {
  offerId.value = "";
  clearTimeout(timer);
  timer = setTimeout(() => searchOffers(offerSearch.value), 200);
});

async function searchOffers(query) {
  const response = await fetch("/api/offers?q=" + encodeURIComponent(query));
  const payload = await response.json();
  offerList.replaceChildren();
  if (!response.ok) {
    offerList.hidden = true;
    showError(payload.detail || "Не удалось найти офферы");
    return;
  }
  offerList.hidden = payload.length === 0;
  for (const offer of payload) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    const countries = (offer.country || []).join(",");
    button.textContent = offer.id + " · " + offer.name + (countries ? " · " + countries : "");
    button.addEventListener("click", () => {
      offerId.value = offer.id;
      offerSearch.value = offer.id + " · " + offer.name;
      offerList.hidden = true;
    });
    item.append(button);
    offerList.append(item);
  }
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError("");
  resultBox.hidden = true;
  if (!offerId.value) {
    showError("Выберите оффер из подсказки");
    return;
  }
  const data = new FormData(form);
  const body = {
    name: data.get("name"),
    geo: data.get("geo"),
    offer_id: Number(offerId.value),
    domain_id: Number(data.get("domain_id")),
    group_id: Number(data.get("group_id")),
    source_id: Number(data.get("source_id")),
  };
  const response = await fetch("/api/campaigns", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) {
    showError(payload.detail || "Кампания не создана");
    return;
  }
  resultBox.hidden = false;
  resultBox.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = "Кампания " + payload.keitaro_id + " создана";
  const text = document.createElement("p");
  text.textContent = payload.name + " · alias " + payload.alias;
  const link = document.createElement("a");
  link.href = "/editor?campaign=" + payload.keitaro_id;
  link.textContent = "Открыть в редакторе";
  resultBox.append(title, text, link);
});

loadMeta();
