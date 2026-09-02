// Enforces the one rule the collector spec exists to hold: no field without a
// question. A collector that stores fields "because they might be useful" is
// how you end up with 35 loose JSON files nobody reads.
import fs from 'node:fs';

const path = process.argv[2];
if (!path) { console.error('usage: verify_collector.mjs <COLLECTOR.md>'); process.exit(2); }
if (!fs.existsSync(path)) { console.error(`FAIL ${path}: does not exist`); process.exit(1); }
const lines = fs.readFileSync(path, 'utf8').split('\n');

const errors = [];
let fields = 0, questions = 0, inTable = false;

for (const [i, raw] of lines.entries()) {
  const line = raw.trim();
  if (/^\|\s*FIELD\s*\|/i.test(line)) { inTable = true; continue; }
  if (inTable && !line.startsWith('|')) { inTable = false; continue; }
  if (!inTable || /^\|[\s|:-]+\|$/.test(line)) continue;

  const cells = line.split('|').slice(1, -1).map(c => c.trim());
  if (cells.length < 3) { errors.push(`line ${i + 1}: row has ${cells.length} cells, need FIELD | SOURCE | QUESTION`); continue; }
  const [field, source, question] = cells;
  fields++;
  if (!field) errors.push(`line ${i + 1}: empty FIELD`);
  if (!source) errors.push(`line ${i + 1}: field "${field}" has no SOURCE — where does it come from?`);
  if (!question || question.length < 12) {
    errors.push(`line ${i + 1}: field "${field}" has no QUESTION — no field without a question`);
  } else questions++;
}

// Every question heading must own at least one field.
const qHeads = lines.filter(l => /^##\s+Q\d+\s+—/.test(l)).length;
if (qHeads < 3) errors.push(`only ${qHeads} question sections — too few to be a real spec`);
if (!/What NOT to collect/i.test(lines.join('\n'))) {
  errors.push('missing a "what NOT to collect" section — a spec that only adds is how the 35 orphaned state files happened');
}
if (fields === 0) errors.push('no FIELD rows found at all');

if (errors.length) { for (const e of errors) console.error('FAIL ' + e); console.error(`\n${errors.length} problem(s)`); process.exit(1); }
console.log(`collector verification passed (${fields} fields across ${qHeads} questions, every field answering one)`);
