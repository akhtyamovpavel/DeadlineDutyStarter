const form = document.querySelector("#deadline-form");
const titleInput = document.querySelector("#title");
const dateInput = document.querySelector("#due-date");
const submitButton = form.querySelector("button[type=submit]");
const refreshButton = document.querySelector("#refresh");
const list = document.querySelector("#deadline-list");
const empty = document.querySelector("#empty");
const status = document.querySelector("#status");
const error = document.querySelector("#error");
const todayHeading = document.querySelector("#today-heading");

async function request(url, options) {
  if (options && options.method && !["GET", "HEAD", "OPTIONS"].includes(options.method)) {
    options.headers = {...options.headers, "X-Requested-With": "DeadlineDuty"};
  }
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function makeItem(deadline) {
  const item = document.createElement("li");
  const details = document.createElement("div");
  const title = document.createElement("strong");
  const date = document.createElement("span");
  const button = document.createElement("button");
  const displayTitle = deadline.title || "Без названия";

  details.className = "deadline-details";
  title.textContent = displayTitle;
  date.className = "deadline-date";
  date.textContent = `Срок: ${deadline.due_date}`;
  button.className = "secondary";
  button.type = "button";
  button.textContent = "Отметить выполненным";
  button.setAttribute("aria-label", `Отметить выполненным: ${displayTitle}`);
  button.addEventListener("click", () => completeDeadline(deadline.id, button));
  details.append(title, date);
  item.append(details, button);
  return item;
}

async function loadDeadlines() {
  refreshButton.disabled = true;
  try {
    const deadlines = await request("/today");
    const items = deadlines.map(makeItem);
    list.replaceChildren(...items);
    empty.hidden = deadlines.length !== 0;
    return true;
  } catch {
    error.textContent = "Не удалось загрузить список. Попробуй обновить его ещё раз.";
    return false;
  } finally {
    refreshButton.disabled = false;
  }
}

async function completeDeadline(id, button) {
  error.textContent = "";
  status.textContent = "";
  button.disabled = true;
  try {
    await request(`/deadlines/${encodeURIComponent(id)}/done`, {method: "POST"});
    status.textContent = "Дедлайн отмечен выполненным.";
    await loadDeadlines();
    todayHeading.focus();
  } catch {
    error.textContent = "Не удалось отметить дедлайн выполненным. Попробуй ещё раз.";
    button.disabled = false;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.textContent = "";
  status.textContent = "";
  submitButton.disabled = true;
  const payload = {title: titleInput.value, due_date: dateInput.value};
  try {
    await request("/deadlines", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    });
    form.reset();
    status.textContent = "Дедлайн добавлен.";
    await loadDeadlines();
  } catch {
    error.textContent = "Не удалось добавить дедлайн. Проверь дату и попробуй ещё раз.";
  } finally {
    submitButton.disabled = false;
  }
});

refreshButton.addEventListener("click", () => {
  error.textContent = "";
  status.textContent = "";
  loadDeadlines();
});

loadDeadlines();
