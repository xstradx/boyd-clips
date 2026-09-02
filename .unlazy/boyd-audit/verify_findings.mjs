#!/usr/bin/env node
// Verifies an audit findings file. Read-only. Fails loudly on any finding that
// lacks real evidence, because a finding without a fetched/measured source is a
// guess wearing a research costume.
import fs from 'node:fs';
import path from 'node:path';

const REQUIRED = ['SEVERITY', 'EVIDENCE', 'WHY-IT-MATTERS', 'PROPOSAL', 'COST'];
const SEVERITIES = new Set(['blocker', 'high', 'medium', 'low']);
const EMPTY = /^(pending|tbd|n\/a|na|none yet|unknown|-|\.)?$/i;

const args = process.argv.slice(2);
const minIdx = args.indexOf('--min');
const min = minIdx >= 0 ? parseInt(args[minIdx + 1], 10) : 1;
const files = args.filter((a, i) => !a.startsWith('--') && (minIdx < 0 || i !== minIdx + 1));
if (!files.length) { console.error('usage: verify_findings.mjs [--min N] <file...>'); process.exit(2); }

let errors = [], total = 0;
for (const f of files) {
  const abs = path.resolve(f);
  if (!fs.existsSync(abs)) { errors.push(`${f}: file does not exist`); continue; }
  const text = fs.readFileSync(abs, 'utf8');
  const blocks = text.split(/^##\s+/m).slice(1);
  if (blocks.length < min) errors.push(`${f}: ${blocks.length} findings, need at least ${min}`);
  for (const b of blocks) {
    const id = b.split('\n')[0].trim();
    if (!/^F\d+\s*:/.test(id)) { errors.push(`${f}: heading is not "F<n>: <claim>" -> ${id.slice(0,60)}`); continue; }
    total++;
    for (const key of REQUIRED) {
      const m = b.match(new RegExp('^' + key + ':(.*)$', 'mi'));
      if (!m) { errors.push(`${f} ${id.split(':')[0]}: missing ${key}`); continue; }
      const val = m[1].trim();
      if (EMPTY.test(val)) errors.push(`${f} ${id.split(':')[0]}: ${key} is empty/placeholder ("${val}")`);
      if (key === 'SEVERITY' && !SEVERITIES.has(val.toLowerCase())) errors.push(`${f} ${id.split(':')[0]}: SEVERITY "${val}" not one of ${[...SEVERITIES].join('|')}`);
      if (key === 'EVIDENCE' && val.length < 25) errors.push(`${f} ${id.split(':')[0]}: EVIDENCE too thin to be a real source ("${val}")`);
    }
  }
}
if (errors.length) { for (const e of errors) console.error('FAIL ' + e); console.error(`\n${errors.length} problem(s) across ${files.length} file(s)`); process.exit(1); }
console.log(`findings verification passed (${total} findings, ${files.length} file(s), min ${min} each)`);
