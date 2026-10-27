const assert = require("node:assert/strict");
const vm = require("node:vm");

class Element {
  constructor() {
    this.children = [];
    this.events = {};
    this.attributes = {};
    this.value = "";
    this.textContent = "";
    this.hidden = false;
    this.disabled = false;
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

  focus() {}
}

async function runScenario() {
  const origin = process.env.WEB_INTEGRATION_ORIGIN;
  const credentials = Buffer.from("test-user:test-password").toString("base64");
  const authenticatedFetch = (path, options = {}) => {
    const headers = {Authorization: `Basic ${credentials}`, ...options.headers};
    return fetch(`${origin}${path}`, {...options, headers});
  };
  const page = await authenticatedFetch("/");
  assert.equal(page.status, 200);
  const html = await page.text();
  assert.match(html, /id="deadline-form"/);
  assert.match(html, /src="\/assets\/app.js"/);

  const javascript = await authenticatedFetch("/assets/app.js");
  assert.equal(javascript.status, 200);
  const source = await javascript.text();

  const selectors = [
    "#deadline-form", "#title", "#due-date", "#refresh", "#deadline-list",
    "#empty", "#status", "#error", "#today-heading",
  ];
  const elements = {};
  for (const selector of selectors) {
    elements[selector] = new Element();
    assert.ok(html.includes(`id="${selector.slice(1)}"`));
  }
  const submitButton = new Element();
  const form = elements["#deadline-form"];
  elements["#empty"].hidden = true;
  form.querySelector = () => submitButton;
  form.reset = () => {
    elements["#title"].value = "";
    elements["#due-date"].value = "";
  };
  const document = {
    querySelector: (selector) => elements[selector],
    createElement: () => new Element(),
  };
  const requests = [];
  const realFetch = (path, options) => {
    const request = authenticatedFetch(path, options);
    requests.push(request);
    return request;
  };
  vm.runInNewContext(source, {document, fetch: realFetch, encodeURIComponent});
  await Promise.all(requests);
  for (let attempt = 0; attempt < 100 && elements["#empty"].hidden; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.equal(elements["#empty"].hidden, false);

  elements["#title"].value = "Проверить сценарий";
  elements["#due-date"].value = "2000-01-01";
  await form.events.submit({preventDefault() {}});
  assert.equal(elements["#status"].textContent, "Дедлайн добавлен.");
  const items = elements["#deadline-list"].children;
  assert.equal(items.length, 1);
  assert.equal(items[0].children[0].children[0].textContent, "Проверить сценарий");
  const todayResponse = await authenticatedFetch("/today");
  const today = await todayResponse.json();
  assert.equal(today.length, 1);
  assert.equal(today[0].title, "Проверить сценарий");
  assert.equal(today[0].done, false);

  await items[0].children[1].events.click();
  assert.equal(elements["#status"].textContent, "Дедлайн отмечен выполненным.");
  assert.equal(elements["#deadline-list"].children.length, 0);
  const afterCompletion = await authenticatedFetch("/today");
  assert.deepEqual(await afterCompletion.json(), []);
}

runScenario().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
