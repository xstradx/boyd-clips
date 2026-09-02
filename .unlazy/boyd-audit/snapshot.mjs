#!/usr/bin/env node
// Snapshots path+size+mtime for everything the audit must NOT touch.
// Excludes .unlazy/ (the audit's own workspace) and work/ (1768 dirs of media).
import fs from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(process.argv[3] || 'C:/Users/natha/Projects/boyd-clips');
const DESK = 'C:/Users/natha/OneDrive/Desktop/Boyd Clips';
const ROOTS = ['src','scripts','spec','docs','config','state','tests','assets','tools','models','research'];
const SKIP = new Set(['.unlazy','work','out','logs','__pycache__','.git','.pytest_cache','.firecrawl','node_modules']);

function walk(dir, out, depth = 0) {
  if (depth > 12) return out;
  let ents; try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of ents) {
    if (SKIP.has(e.name)) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out, depth + 1);
    else if (e.isFile()) { try { const s = fs.statSync(p); out.push(`${p}\t${s.size}\t${Math.round(s.mtimeMs)}`); } catch {} }
  }
  return out;
}

function collect() {
  const out = [];
  for (const r of ROOTS) { const d = path.join(REPO, r); if (fs.existsSync(d)) walk(d, out); }
  for (const f of fs.readdirSync(REPO, { withFileTypes: true })) {
    if (f.isFile()) { const p = path.join(REPO, f.name); const s = fs.statSync(p); out.push(`${p}\t${s.size}\t${Math.round(s.mtimeMs)}`); }
  }
  if (fs.existsSync(DESK)) walk(DESK, out);
  return out.sort();
}

const mode = process.argv[2];
const file = path.join(REPO, '.unlazy/boyd-audit/baseline.tsv');
if (mode === '--write') {
  const rows = collect();
  fs.writeFileSync(file, rows.join('\n') + '\n');
  console.log(`baseline written: ${rows.length} files`);
} else if (mode === '--diff') {
  if (!fs.existsSync(file)) { console.error('no baseline'); process.exit(2); }
  const before = new Map(fs.readFileSync(file, 'utf8').trim().split('\n').map(l => { const [p, ...r] = l.split('\t'); return [p, r.join('\t')]; }));
  const after = new Map(collect().map(l => { const [p, ...r] = l.split('\t'); return [p, r.join('\t')]; }));
  const changed = [], added = [], removed = [];
  for (const [p, v] of after) { if (!before.has(p)) added.push(p); else if (before.get(p) !== v) changed.push(p); }
  for (const p of before.keys()) if (!after.has(p)) removed.push(p);
  for (const [label, list] of [['MODIFIED', changed], ['ADDED', added], ['REMOVED', removed]]) for (const p of list) console.error(`${label} ${p}`);
  const n = changed.length + added.length + removed.length;
  if (n) { console.error(`\n${n} file(s) outside the audit workspace changed — this pass was supposed to be read-only`); process.exit(1); }
  console.log(`read-only verification passed (${after.size} files unchanged since baseline)`);
} else { console.error('usage: snapshot.mjs --write|--diff [repo]'); process.exit(2); }
