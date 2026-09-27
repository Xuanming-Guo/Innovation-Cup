/* global process, fetch, WebSocket, Buffer, setTimeout, clearTimeout, console */
/**
 * Capture a clean, production-component screenshot from a fresh authored-replay run.
 * Start the local host and Vite first, then run this script from the repository root.
 */
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const output = join(here, "../../../../docs/presentation/z3-checker-p1.png");
await mkdir(dirname(output), { recursive: true });
const profile = await mkdtemp(join(tmpdir(), "alto-z3-presentation-"));
const port = 9341;
const browser = spawn(
  process.env.ALTO_BROWSER ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-sandbox",
    "--disable-extensions",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    "about:blank",
  ],
  { windowsHide: true, stdio: "ignore" },
);
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let socket;

try {
  let target;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
      break;
    } catch {
      await pause(100);
    }
  }
  if (!target) throw new Error("Edge remote debugging did not start");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  let serial = 0;
  const pending = new Map();
  const pageErrors = [];
  function send(method, params = {}) {
    const id = ++serial;
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`CDP timeout: ${method}`));
      }, 30000);
      pending.set(id, { resolve, reject, timeout });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  socket.addEventListener("message", (event) => {
    const value = JSON.parse(String(event.data));
    if (value.id) {
      const waiter = pending.get(value.id);
      if (!waiter) return;
      clearTimeout(waiter.timeout);
      pending.delete(value.id);
      if (value.error) waiter.reject(new Error(value.error.message));
      else waiter.resolve(value.result);
    } else if (value.method === "Runtime.exceptionThrown") {
      pageErrors.push(value.params.exceptionDetails.exception?.description ?? value.params.exceptionDetails.text);
    }
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1672,
    height: 941,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `localStorage.setItem("alto.onboarding.maya.v1", JSON.stringify({version:1,stage:"complete",assistantThreadId:"presentation-capture",threadCommandKey:"presentation-thread-key",messageCommandKey:"presentation-message-key",launchCommandKey:"presentation-launch-key"}));`,
  });
  const evaluate = async (expression) => {
    const response = await send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.text);
    return response.result?.value;
  };
  async function waitFor(label, expression, timeoutMs = 120000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (await evaluate(expression)) return;
      await pause(250);
    }
    const state = await evaluate(`({hash:location.hash,text:document.body.innerText.slice(0,2400)})`);
    throw new Error(`Timed out waiting for ${label}: ${JSON.stringify(state)}`);
  }
  async function clickButton(label) {
    const clicked = await evaluate(`(() => { const button=Array.from(document.querySelectorAll('button')).find((item)=>item.textContent.trim()===${JSON.stringify(label)} && !item.disabled); if (!button) return false; button.click(); return true; })()`);
    if (!clicked) throw new Error(`Enabled button not found: ${label}`);
  }

  await send("Page.navigate", { url: "http://127.0.0.1:1420/#/home" });
  await waitFor(
    "the isolated manager workspace",
    `Boolean(document.querySelector('.alto-shell')) && document.body.innerText.includes('Prepare the Northstar launch plan')`,
  );

  await evaluate(`location.hash='#/simulation'`);
  await waitFor("Simulation controls", `document.body.innerText.includes('Create a run') && document.body.innerText.includes('Create isolated run')`);
  await clickButton("Create isolated run");
  await waitFor(
    "the new authored-replay run",
    `document.body.innerText.includes('Current run') && document.body.innerText.toLowerCase().includes('authored replay')`,
  );

  await waitFor("Maya in the actor selector", `(() => { const select=Array.from(document.querySelectorAll('select')).find((item)=>item.closest('label')?.textContent.includes('Explicit demo actor')); return Boolean(select && Array.from(select.options).some((option)=>option.textContent.trim().startsWith('Maya'))); })()`);
  await evaluate(`(() => { const select=Array.from(document.querySelectorAll('select')).find((item)=>item.closest('label')?.textContent.includes('Explicit demo actor')); const option=Array.from(select.options).find((item)=>item.textContent.trim().startsWith('Maya')); const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set; setter.call(select,option.value); select.dispatchEvent(new Event('change',{bubbles:true})); })()`);
  await clickButton("Start labelled actor session");
  await waitFor("the labelled Maya manager session", `document.body.innerText.includes('Demo manager: Maya')`);

  await clickButton("Prepare the Northstar launch plan");
  await waitFor("the saved planning conversation", `location.hash.includes('/home?request=')`);
  await waitFor("the checked P1 plan", `Array.from(document.querySelectorAll('button')).some((item)=>item.textContent.trim()==='Review plan' && !item.disabled)`, 180000);
  await clickButton("Review plan");
  await waitFor("the exact plan review", `Array.from(document.querySelectorAll('button')).some((item)=>item.textContent.trim()==='Open task graph & rules' && !item.disabled)`);
  await clickButton("Open task graph & rules");

  await waitFor("the strict Z3 checker summary", `document.body.innerText.includes('SAT · CHECKED') && document.body.innerText.includes('157 / 157')`);
  await evaluate(`document.querySelector('[data-rule-category="protected_time"]')?.click()`);
  await waitFor("the protected-capacity rule", `Array.from(document.querySelectorAll('[data-rule-id]')).some((item)=>item.textContent.trim()==='protected.priya.tuesday')`);
  await evaluate(`Array.from(document.querySelectorAll('[data-rule-id]')).find((item)=>item.textContent.trim()==='protected.priya.tuesday')?.click()`);
  await waitFor("the persisted technical expression", `Boolean(document.querySelector('.alto-raw-assertion')) && !document.querySelector('.alto-raw-assertion')?.textContent.includes('Loading')`);
  await evaluate(`document.querySelector('.alto-raw-assertion > summary')?.click()`);
  await waitFor("the expanded raw assertion", `document.querySelector('.alto-raw-assertion pre')?.textContent.includes('(and (<= 1 1)')`);
  await evaluate(`document.querySelector('.alto-raw-assertion')?.scrollIntoView({block:'nearest'})`);
  await pause(500);

  const evidence = await evaluate(`({
    hash: location.hash,
    dimensions: [innerWidth, innerHeight],
    checked: document.body.innerText.includes('SAT · CHECKED'),
    authoredReplay: document.body.innerText.toLowerCase().includes('authored replay'),
    synthetic: document.body.innerText.toLowerCase().includes('synthetic'),
    demoActor: document.body.innerText.includes('Demo manager: Maya'),
    raw: document.querySelector('.alto-raw-assertion pre')?.textContent ?? null,
    visibleText: document.body.innerText,
  })`);
  if (!evidence.checked || !evidence.authoredReplay || !evidence.synthetic || !evidence.demoActor || !evidence.raw) {
    throw new Error(`Required presentation labels are missing: ${JSON.stringify({ ...evidence, visibleText: undefined })}`);
  }
  if (/(?:bearer\s+[a-z0-9._-]+|eyJ[a-zA-Z0-9_-]{20,}|password\s*[:=]|api[_ -]?key\s*[:=])/i.test(evidence.visibleText)) {
    throw new Error("Potential credential-like text is visible; capture refused");
  }
  if (pageErrors.length) throw new Error(`Browser exceptions: ${pageErrors.join(" | ")}`);

  const capture = await send("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  await writeFile(output, Buffer.from(capture.data, "base64"));
  console.log(`Captured ${output}`);
  console.log(`Viewport ${evidence.dimensions.join("x")} · authored replay · persisted raw assertion`);
} finally {
  socket?.close();
  browser.kill();
}
