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
  assert.ok(html.includes("M-series chips use the Apple silicon build"));
  assert.ok(html.includes("Windows is unsigned"));
  assert.ok(html.includes("not notarized"));
});

test("includes the expected accessibility and responsive safeguards", () => {
  assert.ok(html.includes('href="#downloads"'));
  assert.ok(html.includes('id="hero-title"'));
  assert.ok(html.includes('id="downloads-title"'));
  assert.match(css, /:focus-visible/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(css, /@media \(max-width: 720px\)/);
  assert.match(css, /min-width:\s*320px/);
});

