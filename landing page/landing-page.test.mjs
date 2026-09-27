import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const directory = new URL("./", import.meta.url);
const html = await readFile(new URL("index.html", directory), "utf8");
const css = await readFile(new URL("styles.css", directory), "utf8");

const expectedDownloads = [
  ["ALTO-mac-apple-silicon.dmg", "Download ALTO for Mac with Apple silicon"],
  ["ALTO-windows-x64-setup.exe", "Download ALTO for Windows x64"],
  ["ALTO-mac-intel.dmg", "Download ALTO for Mac with an Intel processor"],
];

test("exposes exactly three stable native download links", () => {
  const downloadLinks = [...html.matchAll(/href="([^"]+\/releases\/latest\/download\/[^"]+)"/g)];
  assert.equal(downloadLinks.length, 3);
  assert.equal(new Set(downloadLinks.map((match) => match[1])).size, 3);

  for (const [filename, accessibleName] of expectedDownloads) {
    assert.match(html, new RegExp(`releases/latest/download/${filename.replaceAll(".", "\\.")}`));
    assert.ok(html.includes(`aria-label="${accessibleName}"`));
  }
});

test("keeps compatibility and release limitations visible", () => {
  assert.ok(html.includes("macOS 13+"));
  assert.ok(html.includes("Windows 11"));
  assert.ok(html.includes("Windows is unsigned"));
  assert.ok(html.includes("not notarized"));
  assert.ok(html.includes("System Settings &rarr; Privacy &amp; Security"));
  assert.ok(html.includes("Open Anyway"));
  assert.ok(html.includes("do not\n                need to disable Gatekeeper"));
  assert.equal((html.match(/Opening steps below/g) ?? []).length, 2);
});

test("embeds the demo video and links the external Data Room safely", () => {
  const heroIndex = html.indexOf('class="hero"');
  const showcaseIndex = html.indexOf('class="showcase"');
  const downloadsIndex = html.indexOf('class="downloads"');

  assert.ok(heroIndex < showcaseIndex && showcaseIndex < downloadsIndex);
  assert.match(html, /<video\s+controls\s+playsinline\s+preload="metadata"/);
  assert.ok(html.includes('aria-label="Watch the ALTO product demo"'));
  assert.ok(html.includes('<source src="./alto-demo.mp4" type="video/mp4"'));
  assert.ok(html.includes('<a href="./alto-demo.mp4">Download the ALTO demo video.</a>'));
  assert.ok(html.includes('<a href="./alto-demo.mp4">Open video file</a>'));
  assert.doesNotMatch(html, /<video[^>]*\bautoplay\b/);

  assert.ok(html.includes("https://drive.google.com/drive/folders/1H0xRJpa73xkRBztrmQzJI5bub6HVkQe3?usp=sharing"));
  assert.ok(html.includes('target="_blank"'));
  assert.ok(html.includes('rel="noopener noreferrer"'));
  assert.ok(html.includes("Open Data Room"));
  assert.match(css, /\.showcase-grid\s*{[^}]*display:\s*grid/s);
});

test("includes the expected accessibility and responsive safeguards", () => {
  assert.ok(html.includes('href="#downloads"'));
  assert.ok(html.includes('id="hero-title"'));
  assert.ok(html.includes('id="downloads-title"'));
  assert.ok(html.includes("Every change,"));
  assert.ok(html.includes("coordinated."));
  assert.ok(!html.includes("Human-led coordination"));
  assert.ok(!html.includes("Choose your build"));
  assert.match(css, /:focus-visible/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /min-width:\s*320px/);
});
