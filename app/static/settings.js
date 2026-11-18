const form = document.querySelector("#settings-form");
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(form);
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      base_url: data.get("base_url"),
      api_key: data.get("api_key") || "",
    }),
  });
  const payload = await response.json();
  document.querySelector("#settings-ok").hidden = !response.ok;
  const error = document.querySelector("#settings-error");
  error.hidden = response.ok;
  error.textContent = response.ok ? "" : (payload.detail || "Не сохранилось");
});
