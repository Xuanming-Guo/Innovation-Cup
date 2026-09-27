/* global process, fetch, WebSocket, Buffer, setTimeout, clearTimeout, console */
/** Four isolated browser-fixture captures. No live backend, credentials or provider.
 * Reuses the existing test harness, but never overwrites storyboard evidence.
 * Start Vite on localhost:1420, then run this file with Node.
 */
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const outputFolder = process.env.ALTO_VISUAL_OUTPUT_FOLDER ?? "autonomous-planning-visual-artifacts";
if (!/^[a-z0-9-]+$/.test(outputFolder)) throw new Error("Capture output must be a single folder name inside the test directory.");
const output = join(dirname(fileURLToPath(import.meta.url)), outputFolder);
await mkdir(output, { recursive: true });
const port = 9338;
let occupied = false;
try { await fetch(`http://127.0.0.1:${port}/json/version`); occupied = true; } catch { /* Dedicated port is free. */ }
if (occupied) throw new Error("Dedicated capture port is already in use; refusing to control another browser.");
const profile = await mkdtemp(join(tmpdir(), "alto-planning-visual-"));
const browser = spawn(process.env.ALTO_BROWSER ?? "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", ["--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--disable-extensions", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, "about:blank"], { windowsHide: true, stdio: "ignore" });
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let socket;
let serial = 0;
try {
  let target;
  for (let attempt = 0; attempt < 80; attempt++) {
    try { target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json(); break; } catch { await pause(100); }
  }
  if (!target) throw new Error("Dedicated Edge instance did not start.");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener("open", resolve, { once: true }); socket.addEventListener("error", reject, { once: true }); });
  const pending = new Map();
  const errors = [];
  function send(method, params = {}) {
    const id = ++serial;
    return new Promise((resolve, reject) => { const timeout = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 10000); pending.set(id, { resolve, reject, timeout }); socket.send(JSON.stringify({ id, method, params })); });
  }
  socket.addEventListener("message", (event) => {
    const value = JSON.parse(String(event.data));
    if (value.id) {
      const waiter = pending.get(value.id);
      if (waiter) { clearTimeout(waiter.timeout); pending.delete(value.id); if (value.error) waiter.reject(new Error(value.error.message)); else waiter.resolve(value.result); }
    } else if (value.method === "Fetch.requestPaused") {
      void send("Fetch.fulfillRequest", { requestId: value.params.requestId, responseCode: 200, responseHeaders: [{ name: "Content-Type", value: "text/javascript" }], body: Buffer.from('import "/src/test/visual-harness.tsx";').toString("base64") });
    } else if (value.method === "Runtime.exceptionThrown") errors.push(value.params.exceptionDetails.exception?.description ?? value.params.exceptionDetails.text);
  });
  const version = (await send("Browser.getVersion")).product;
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Fetch.enable", { patterns: [{ urlPattern: "*/src/main.tsx*", requestStage: "Request" }] });
  await send("Emulation.setDeviceMetricsOverride", { width: 1672, height: 941, deviceScaleFactor: 1, mobile: false });
  const evaluate = async (expression) => { const response = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }); if (response.exceptionDetails) throw new Error(response.exceptionDetails.text); return response.result?.value; };
  const waitFor = async (expression) => { for (let attempt = 0; attempt < 80; attempt++) { await pause(100); if (await evaluate(expression)) return; } throw new Error(`Capture did not become ready: ${expression}`); };
  const cases = [
    { id: "F01-demo-role-chooser", route: "/settings/demo", ready: "document.body.innerText.includes('Continue as manager')" },
    { id: "F02-plan-request-preview", route: "/home", ready: "Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Plan work')", interact: async () => {
      await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Plan work').click()");
      await evaluate("{ const input=document.querySelector('[aria-label=\"Message ALTO\"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'Prepare the Northstar product launch for Friday. Coordinate release, launch materials and support while preserving existing commitments.'); input.dispatchEvent(new Event('input',{bubbles:true})); }");
      await pause(80);
      await evaluate("document.querySelector('[aria-label=\"Send message\"]').click()");
      await waitFor("document.body.innerText.includes('Use approved Northstar request')");
    } },
    { id: "F03-stopped-planning-conversation", route: "/home?request=visual-failed", ready: "document.body.innerText.includes('Planning stopped — not awaiting your approval')" },
    { id: "F04-active-planning", route: "/home?request=visual-active", ready: "Boolean(document.querySelector('.alto-planning-spinner'))" },
  ];
  const captures = [];
  for (const entry of cases) {
    errors.length = 0;
    await send("Page.navigate", { url: `http://127.0.0.1:1420/?visual=manager&capture=${entry.id}#${entry.route}` });
    await waitFor(`Boolean(document.querySelector('.alto-shell')) && document.body.innerText.includes('FIXTURE DATA') && (${entry.ready})`);
    if (entry.interact) await entry.interact();
    const logos = await evaluate("Promise.all(Array.from(document.querySelectorAll('.alto-logo svg image')).map(async node => { const source=node.href.baseVal; const img=new Image(); img.src=source; await img.decode(); if (!img.naturalWidth) throw new Error('Logo failed to decode'); return {source,naturalWidth:img.naturalWidth,naturalHeight:img.naturalHeight,viewBox:node.ownerSVGElement.getAttribute('viewBox')}; }))");
    if (!logos.length || logos.some((logo) => !logo.source.includes("LOGO.jpeg"))) throw new Error("The supplied JPEG logo is not rendered and decoded.");
    await pause(300);
    const page = await evaluate("({title:document.title,heading:document.querySelector('h1,h2')?.textContent??null,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,viewportWidth:innerWidth,alerts:Array.from(document.querySelectorAll('[role=alert]')).map(n=>n.textContent),refreshChatter:/Updating (in the background|this saved request)/.test(document.body.innerText),spinnerCount:document.querySelectorAll('.alto-planning-spinner').length})");
    if (page.refreshChatter) throw new Error("Successful refresh chatter is visible.");
    if (entry.id === "F03-stopped-planning-conversation" && page.spinnerCount !== 0) throw new Error("Stopped planning is incorrectly animated.");
    let spinner = null;
    if (entry.id === "F04-active-planning") {
      const readSpinner = "(() => { const node=document.querySelector('.alto-planning-spinner'); const style=getComputedStyle(node); return {animation:style.animationName,duration:style.animationDuration,label:node.parentElement.getAttribute('aria-label'),live:node.parentElement.getAttribute('aria-live')}; })()";
      spinner = await evaluate(readSpinner);
      if (page.spinnerCount !== 1 || spinner.animation === "none") throw new Error("Running planning has no active animated circle.");
      await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
      spinner.reducedMotionAnimation = (await evaluate(readSpinner)).animation;
      if (spinner.reducedMotionAnimation !== "none") throw new Error("Planning animation ignores reduced motion.");
      await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "no-preference" }] });
    }
    const screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    await writeFile(join(output, `${entry.id}.png`), Buffer.from(screenshot.data, "base64"));
    captures.push({ id: entry.id, route: entry.route, file: `${entry.id}.png`, ...page, logos, spinner, errors: [...errors], evidence: "browser fixture only; no live model, backend or installed-native claim" });
    console.log(`${entry.id}: errors=${errors.length}, horizontalOverflow=${page.scrollWidth > page.viewportWidth}`);
  }
  await writeFile(join(output, "manifest.json"), JSON.stringify({ generated_at: new Date().toISOString(), browser: version, viewport: "1672x941", captures }, null, 2));
  if (captures.some((capture) => capture.errors.length)) process.exitCode = 1;
  console.log(`Fixture captures saved to ${output}`);
} finally {
  // This CDP endpoint belongs only to the dedicated temporary-profile process.
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ id: ++serial, method: "Browser.close" }));
  await pause(200);
  socket?.close();
  browser.kill();
}
