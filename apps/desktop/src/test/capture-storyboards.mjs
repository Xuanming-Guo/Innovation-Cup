/* global process, fetch, WebSocket, Buffer, setTimeout, clearTimeout, console */
/** Local browser-only visual evidence, not live integration or installed native proof.
 * Start Vite first, then run: node apps/desktop/src/test/capture-storyboards.mjs
 * The production entry is replaced in CDP only; no application code loads the harness.
 */
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const output = join(dirname(fileURLToPath(import.meta.url)), "visual-artifacts");
await mkdir(output, { recursive: true });
const profile = await mkdtemp(join(tmpdir(), "alto-visual-"));
const browser = spawn(process.env.ALTO_BROWSER ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", ["--headless=new", "--disable-gpu", "--no-first-run", "--no-sandbox", "--disable-extensions", "--remote-debugging-port=9337", `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let socket;
try {
  let target;
  for (let attempt = 0; attempt < 100; attempt++) {
    try { target = await (await fetch("http://127.0.0.1:9337/json/new?about:blank", { method: "PUT" })).json(); break; } catch { await pause(100); }
  }
  if (!target) throw new Error("Edge remote debugging did not start");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
  let serial = 0;
  const pending = new Map();
  const errors = [];
  function send(method, params = {}) {
    const id = ++serial;
    return new Promise((resolve, reject) => { const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 15000); pending.set(id, { resolve, reject, timeout }); socket.send(JSON.stringify({ id, method, params })); });
  }
  socket.addEventListener("message", (event) => {
    const value = JSON.parse(String(event.data));
    if (value.id) { const waiter = pending.get(value.id); if (waiter) { clearTimeout(waiter.timeout); pending.delete(value.id); if (value.error) waiter.reject(new Error(value.error.message)); else waiter.resolve(value.result); } }
    else if (value.method === "Fetch.requestPaused") void send("Fetch.fulfillRequest", { requestId: value.params.requestId, responseCode: 200, responseHeaders: [{ name: "Content-Type", value: "text/javascript" }], body: Buffer.from('import "/src/test/visual-harness.tsx";').toString("base64") });
    else if (value.method === "Runtime.exceptionThrown") errors.push(value.params.exceptionDetails.exception?.description ?? value.params.exceptionDetails.text);
  });
  console.log(`Browser: ${(await send("Browser.getVersion")).product}`);
  await send("Page.enable"); await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/src/main.tsx*", requestStage: "Request" }] });
  await send("Emulation.setDeviceMetricsOverride", { width: 1672, height: 941, deviceScaleFactor: 1, mobile: false });
  const evaluate = async (expression) => { const response = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }); if (response.exceptionDetails) throw new Error(response.exceptionDetails.text); return response.result?.value; };
  const click = (label) => evaluate(`document.querySelector('[aria-label=${JSON.stringify(label)}]')?.click()`);
  const ask = async () => { await evaluate(`{ const input=document.querySelector('.alto-composer input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'Summarise the launch commitments.'); input.dispatchEvent(new Event('input',{bubbles:true})); }`); await pause(100); await click("Send message"); };
  const openProtectedEvidence = async () => {
    await evaluate(`document.querySelector('[data-rule-category="protected_time"]')?.click()`);
    for (let attempt = 0; attempt < 40; attempt++) {
      await pause(50);
      if (await evaluate(`Boolean(document.querySelector('[data-rule-id="81000000-0000-4000-8000-000000000009"]'))`)) break;
    }
    await evaluate(`document.querySelector('[data-rule-id="81000000-0000-4000-8000-000000000009"]')?.click()`);
    for (let attempt = 0; attempt < 40; attempt++) {
      await pause(50);
      if (await evaluate(`document.querySelector('.alto-raw-assertion')?.textContent.includes('Raw Z3 assertion')`)) break;
    }
    await evaluate(`document.querySelector('.alto-raw-assertion > summary')?.click()`);
    for (let attempt = 0; attempt < 40; attempt++) {
      await pause(50);
      if (await evaluate(`document.querySelector('.alto-raw-assertion pre')?.textContent.includes('(and (<= 1 1)')`)) break;
    }
    await evaluate(`document.querySelector('.alto-raw-assertion')?.scrollIntoView({block:'nearest'})`);
  };
  const cases = [
    ["M01", "manager", "/home"], ["M02", "manager", "/home", () => click("Collapse sidebar")],
    ["M03", "manager", "/home", ask],
    ["M04", "manager", "/home", () => click("Open notifications")],
    ["M05", "manager", "/projects"], ["M06", "manager", "/projects?status=completed"],
    ["M07", "manager", "/projects/northstar/graph?panel=rules", openProtectedEvidence], ["M08", "manager", "/projects/northstar/graph?task=E1", ask],
    ["M09", "employee", "/projects/northstar/graph?task=E1", () => evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Open work'))?.click()`)],
    ["M10", "manager", "/calendar", () => evaluate(`document.querySelector('.alto-calendar-event.work')?.click()`)], ["M11", "manager", "/people/jordan"],
    ["M12", "manager", "/settings/connections"], ["M13", "manager", "/settings/workspace"],
    ["M14", "manager", "/assistant/overlay"],
    ["E01", "employee", "/home"], ["E02", "employee", "/profile"], ["E03", "employee", "/calendar"],
    ["E04", "employee", "/tasks/E1"], ["E05", "employee", "/projects/northstar/graph?task=E1"],
  ];
  const manifest = [];
  for (const [id, role, route, interaction] of cases) {
    errors.length = 0;
    await send("Page.navigate", { url: `http://127.0.0.1:1420/?visual=${role}&capture=${id}#${route}` });
    for (let attempt = 0; attempt < 100; attempt++) { await pause(100); if (await evaluate(`Boolean(document.querySelector('.alto-shell,.alto-native-overlay')) && !document.querySelector('.alto-loading') && document.body.innerText.includes('FIXTURE DATA')`)) break; }
    if (interaction) await interaction();
    await pause(350);
    const page = await evaluate(`({ title:document.title, heading:document.querySelector('h1')?.textContent??null, width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,alerts:Array.from(document.querySelectorAll('[role=alert]')).map(n=>n.textContent),dialogs:document.querySelectorAll('[role=dialog]').length,conversation:document.querySelectorAll('.alto-message').length })`);
    const capture = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    await writeFile(join(output, `${id}.png`), Buffer.from(capture.data, "base64"));
    manifest.push({ id, role, route, viewport: "1672x941", file: `${id}.png`, ...page, errors: [...errors], evidence: "browser fixture only; not live/native verification" });
    console.log(`${id}: ${page.heading ?? "overlay"}; dialogs=${page.dialogs}; errors=${errors.length}; alerts=${page.alerts.length}`);
  }
  await writeFile(join(output, "manifest.json"), JSON.stringify({ generated_at: new Date().toISOString(), excluded: { M15: "Live microphone/provider/scanner and installed native permissions not available; no fake waveform generated." }, captures: manifest }, null, 2));
  if (manifest.some((entry) => entry.errors.length || entry.alerts.length)) process.exitCode = 1;
  console.log(`Captured ${manifest.length} fixture-only states to ${output}`);
} finally { socket?.close(); browser.kill(); }
