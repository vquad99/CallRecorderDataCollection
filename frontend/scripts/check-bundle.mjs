// Bundle budget (owner's list, O11): what the first screen downloads, compressed, and the largest
// page loaded on demand. Run after `npm run build`; fails when a limit is passed, so growth needs
// a decision instead of slipping in.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const FIRST_SCREEN_KB = 115; // 2026-11-10: about 109 KB (React, router, shell, sign-in, Projects)
const PAGE_KB = 30; // 2026-11-10: largest page (recorder) about 6 KB

const dir = "dist/assets";
const kb = (file) => gzipSync(readFileSync(join(dir, file))).length / 1024;
const html = readFileSync("dist/index.html", "utf8");
const entry = /src="\/assets\/([^"]+\.js)"/.exec(html)?.[1];
if (!entry) throw new Error("no entry script in dist/index.html");

// Everything the entry imports statically, followed recursively.
const first = new Set();
const visit = (file) => {
  if (first.has(file)) return;
  first.add(file);
  const code = readFileSync(join(dir, file), "utf8");
  for (const m of code.matchAll(/(?:from|import)\s*"\.\/([^"]+\.js)"/g)) visit(m[1]);
};
visit(entry);

const firstKb = [...first].reduce((n, f) => n + kb(f), 0);
const css = readdirSync(dir)
  .filter((f) => f.endsWith(".css"))
  .reduce((n, f) => n + kb(f), 0);
const pages = readdirSync(dir)
  .filter((f) => f.endsWith(".js") && !first.has(f))
  .map((f) => [f, kb(f)])
  .sort((a, b) => b[1] - a[1]);
const [largest, largestKb] = pages[0] ?? ["none", 0];
console.log(
  `first screen ${(firstKb + css).toFixed(1)} KB compressed (${first.size} files, limit ${FIRST_SCREEN_KB} KB); ` +
    `${pages.length} pages on demand, largest ${largest} ${largestKb.toFixed(1)} KB (limit ${PAGE_KB} KB)`,
);
const problems = [];
if (firstKb + css > FIRST_SCREEN_KB) problems.push("first screen is over its limit");
if (largestKb > PAGE_KB) problems.push(`${largest} is over the page limit`);
if (problems.length) {
  console.error(problems.join("; "));
  process.exit(1);
}
