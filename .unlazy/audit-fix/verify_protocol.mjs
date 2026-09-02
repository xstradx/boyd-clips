// A protocol rule is only worth having if a real failure produced it.
// This refuses any rule whose FAILURE section is generic — it must cite a
// specific artifact of the audit: a leaf id, a file:line, or a measured number.
import fs from 'node:fs';

const path = process.argv[2];
if (!path) { console.error('usage: verify_protocol.mjs <PROTOCOL.md>'); process.exit(2); }
if (!fs.existsSync(path)) { console.error(`FAIL ${path}: does not exist`); process.exit(1); }
const text = fs.readFileSync(path, 'utf8');

const SECTIONS = ['FAILURE', 'MECHANISM', 'ENFORCED-BY'];
// Evidence that a failure is real and from here, not invented best practice.
const CITES = /(leaf-\d\.\d|STATE\.md|CLAUDE\.md|\w+\.(py|mjs|js|json|md|ps1|mp4|jpg)|:\d+|\b\d+(\.\d+)?\s*(dB|spans?|%|of \d+)|\bR\d\b)/;

const blocks = text.split(/^##\s+/m).slice(1);
const errors = [];
if (blocks.length < 5) errors.push(`only ${blocks.length} rules — a protocol this thin is not derived from anything`);

const ids = new Set();
for (const b of blocks) {
  const head = b.split('\n')[0].trim();
  const id = (head.match(/^(R\d+)\b/) || [])[1];
  if (!id) { errors.push(`rule heading must start "R<n>: <rule>" -> ${head.slice(0, 60)}`); continue; }
  if (ids.has(id)) errors.push(`${id}: duplicate rule id`);
  ids.add(id);
  // Line-based, not regex-with-lookahead. The regex version captured only the
  // first line of each section, because JS has no \Z and `$` under /m stops at
  // the newline. That is the identical bug the findings parser had; it came
  // back here because this file had no selftest to catch it.
  const sect = {};
  { let cur = null, buf = [];
    const flush = () => { if (cur) sect[cur] = buf.join('\n').trim(); cur = null; buf = []; };
    for (const line of b.split('\n').slice(1)) {
      const hit = line.match(/^([A-Z][A-Z\-]*):(.*)$/);
      if (hit && SECTIONS.includes(hit[1])) { flush(); cur = hit[1]; buf = [hit[2]]; }
      else if (cur) buf.push(line);
    }
    flush(); }

  for (const s of SECTIONS) {
    const val = (sect[s] || '').trim();
    if (!val) { errors.push(`${id}: missing ${s}`); continue; }
    if (s === 'FAILURE' && !CITES.test(val)) {
      errors.push(`${id}: FAILURE cites nothing specific — a rule with no observed failure behind it is invented best practice`);
    }
    if (val.length < 60) errors.push(`${id}: ${s} is too thin to be a real account (${val.length} chars)`);
  }
}

if (errors.length) { for (const e of errors) console.error('FAIL ' + e); console.error(`\n${errors.length} problem(s)`); process.exit(1); }
console.log(`protocol verification passed (${blocks.length} rules, each citing a real failure)`);
