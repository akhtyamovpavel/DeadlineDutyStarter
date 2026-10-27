const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tag = tag;
    this.children = [];
    this.events = {};
    this.attributes = {};
    this.textContent = "";
    this.value = "";
    this.disabled = false;
    this.hidden = false;
  }

  set innerHTML(value) {
    throw new Error("User content must not be inserted as HTML");
  }

  addEventListener(name, handler) {
    this.events[name] = handler;
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  focus() {
    this.focused = true;
  }
}

function createPage(fetch) {
  const elements = {};
  const selectors = [
    "#deadline-form", "#title", "#due-date", "#refresh", "#deadline-list",
    "#empty", "#status", "#error", "#today-heading",
  ];
  for (const selector of selectors) {
    elements[selector] = new Element();
  }
  const submit = new Element("button");
  const form = elements["#deadline-form"];
  form.querySelector = () => submit;
  form.reset = () => {
    elements["#title"].value = "";
    elements["#due-date"].value = "";
  };
  const document = {
    querySelector: (selector) => elements[selector],
    createElement: (tag) => new Element(tag),
  };
  const source = fs.readFileSync("app/static/app.js", "utf8");
  const context = {document, fetch, encodeURIComponent};
  vm.runInNewContext(source, context);
  return {elements, submit};
}

function response(body, ok = true) {
  return {ok, status: ok ? 200 : 500, json: async () => body};
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
}

test("создание и выполнение обновляют список и сохраняют текст названия", async () => {
  const calls = [];
  const title = '<img src=x onerror="alert(1)">';
  let deadlines = [];
  const fetch = async (url, options = {}) => {
    calls.push({url, options});
    if (url === "/today") {
      return response(deadlines);
    }
    if (url === "/deadlines") {
      const payload = JSON.parse(options.body);
      deadlines = [{id: 1, title: payload.title, due_date: payload.due_date}];
      return response(deadlines[0]);
    }
    if (url === "/deadlines/1/done") {
      deadlines = [];
      return response({id: 1, done: true});
    }
    throw new Error(`Unexpected request: ${url}`);
  };
  const {elements} = createPage(fetch);
  await settle();
  assert.equal(elements["#empty"].hidden, false);

  elements["#title"].value = title;
  elements["#due-date"].value = "2026-01-15";
  await elements["#deadline-form"].events.submit({preventDefault() {}});
  assert.equal(elements["#status"].textContent, "Дедлайн добавлен.");
  const item = elements["#deadline-list"].children[0];
  assert.equal(item.children[0].children[0].textContent, title);
  assert.equal(item.children[0].children[0].children.length, 0);
  assert.equal(item.children[1].attributes["aria-label"], `Отметить выполненным: ${title}`);

  await item.children[1].events.click();
  assert.equal(elements["#status"].textContent, "Дедлайн отмечен выполненным.");
  assert.equal(elements["#deadline-list"].children.length, 0);
  assert.equal(elements["#empty"].hidden, false);
  assert.equal(elements["#today-heading"].focused, true);
  assert.equal(calls[1].url, "/deadlines");
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[3].url, "/deadlines/1/done");
});

test("ошибка сохранения не стирает введённые данные и позволяет повторить", async () => {
  let fail = true;
  const fetch = async (url) => {
    if (url === "/today") {
      return response([]);
    }
    if (fail) {
      throw new Error("Network error");
    }
    return response({id: 1});
  };
  const {elements, submit} = createPage(fetch);
  await settle();
  elements["#title"].value = "Отчёт";
  elements["#due-date"].value = "2026-01-15";
  await elements["#deadline-form"].events.submit({preventDefault() {}});
  assert.match(elements["#error"].textContent, /Не удалось добавить/);
  assert.equal(elements["#title"].value, "Отчёт");
  assert.equal(elements["#due-date"].value, "2026-01-15");
  assert.equal(submit.disabled, false);

  fail = false;
  await elements["#deadline-form"].events.submit({preventDefault() {}});
  assert.equal(elements["#error"].textContent, "");
  assert.equal(elements["#status"].textContent, "Дедлайн добавлен.");
});

test("ошибку загрузки можно исправить повторным обновлением", async () => {
  let fail = true;
  const fetch = async () => {
    if (fail) {
      return response(null, false);
    }
    return response([]);
  };
  const {elements} = createPage(fetch);
  await settle();
  assert.match(elements["#error"].textContent, /Не удалось загрузить/);
  assert.equal(elements["#refresh"].disabled, false);

  fail = false;
  elements["#refresh"].events.click();
  await settle();
  assert.equal(elements["#error"].textContent, "");
  assert.equal(elements["#empty"].hidden, false);
});

test("будущий дедлайн подтверждается, даже если список на сегодня пуст", async () => {
  const fetch = async (url) => {
    if (url === "/today") {
      return response([]);
    }
    return response({id: 1, title: "Завтра", due_date: "2099-01-01"});
  };
  const {elements} = createPage(fetch);
  await settle();
  elements["#title"].value = "Завтра";
  elements["#due-date"].value = "2099-01-01";
  await elements["#deadline-form"].events.submit({preventDefault() {}});
  assert.equal(elements["#status"].textContent, "Дедлайн добавлен.");
  assert.equal(elements["#empty"].hidden, false);
  assert.equal(elements["#deadline-list"].children.length, 0);
});

test("ошибку отметки можно повторить без перезагрузки страницы", async () => {
  let fail = true;
  const deadline = {id: 1, title: "Отчёт", due_date: "2026-01-15"};
  const fetch = async (url) => {
    if (url === "/today") {
      if (fail) {
        return response([deadline]);
      }
      return response([]);
    }
    if (fail) {
      return response(null, false);
    }
    return response({id: 1, done: true});
  };
  const {elements} = createPage(fetch);
  await settle();
  const button = elements["#deadline-list"].children[0].children[1];
  await button.events.click();
  assert.match(elements["#error"].textContent, /Не удалось отметить/);
  assert.equal(button.disabled, false);

  fail = false;
  await button.events.click();
  assert.equal(elements["#error"].textContent, "");
  assert.equal(elements["#deadline-list"].children.length, 0);
});
