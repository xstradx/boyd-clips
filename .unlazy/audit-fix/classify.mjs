// Applies PROTOCOL to the findings the first audit already produced.
// It does NOT rewrite them. It reports which ones would survive the rules and
// which would be sent back, plus every numeric contradiction between leaves.
import fs from 'node:fs';
import path from 'node:path';
import { parse, checkFinding, crosscheck } from './lib.mjs';

const DIR = path.resolve('.unlazy/boyd-audit/findings');
const files = fs.readdirSync(DIR).filter(f => f.startsWith('leaf-')).sort()
  .map(f => ({ name: f, findings: parse(fs.readFileSync(path.join(DIR, f), 'utf8')) }));

const RUNNABLE = /(ffmpeg|ffprobe|yt-dlp|sqlite3|md5sum|python|node|grep\s|rg\s|git\s+(log|show|status|blame|ls-files)|Get-ScheduledTask|ls\s|find\s)/;
const PARAMS = /(?:^|[\s(`'"])(--?[a-zA-Z][\w-]*|[a-z_]+=[^\s]+|-?\d+(?:\.\d+)?\s*dB|d=\d)/;
const INFER = /\b(so|therefore|which means|implies|suggests|indicates|appears to|likely|must have|would have)\b/i;

let total = 0;
const bucket = { measurement: [], inference: [], reading: [] };
const needsControls = [];

for (const { name, findings } of files) {
  for (const fi of findings) {
    if (!/^F\d+$/.test(fi.id)) continue;
    total++;
    const ev = fi.f.EVIDENCE || '';
    const qualified = RUNNABLE.test(ev) && PARAMS.test(ev);
    const inferential = INFER.test(fi.head) || INFER.test(ev);
    const cls = qualified ? (inferential ? 'inference' : 'measurement') : (RUNNABLE.test(ev) ? 'inference' : 'reading');
    bucket[cls].push(`${name}:${fi.id}`);
    const problems = checkFinding({ ...fi, f: { ...fi.f, CLAIM: cls } }, { requireControls: true });
    if (problems.some(p => p.includes('CONTROL'))) needsControls.push(`${name}:${fi.id}`);
  }
}

console.log(`\nFINDINGS CLASSIFIED (heuristic, flagged for review — not asserted correct)\n`);
console.log(`  total findings                       ${total}`);
console.log(`  would stand as MEASUREMENT           ${bucket.measurement.length}   (command + parameters present)`);
console.log(`  would be sent back as INFERENCE      ${bucket.inference.length}   (must declare RESTS-ON + ASSUMES)`);
console.log(`  would be sent back as READING        ${bucket.reading.length}   (no re-runnable command at all)`);
console.log(`  about a checker, but missing controls ${needsControls.length}   (PROTOCOL R4)`);

const conflicts = crosscheck(files);
console.log(`\nNUMERIC CONTRADICTIONS BETWEEN LEAVES (PROTOCOL R7)\n`);
if (!conflicts.length) console.log('  none detected');
else {
  const byArt = {};
  for (const c of conflicts) (byArt[c.artifact] ||= []).push(c);
  const ranked = Object.entries(byArt).sort((a, b) => b[1].length - a[1].length).slice(0, 12);
  for (const [art, cs] of ranked) {
    console.log(`  ${art}  (${cs.length} conflicting pair${cs.length > 1 ? 's' : ''})`);
    for (const c of cs.slice(0, 3)) console.log(`      ${c.unit.padEnd(7)} ${c.a}  vs  ${c.b}`);
  }
  console.log(`\n  ${conflicts.length} conflicting pairs across ${Object.keys(byArt).length} artifacts.`);
  console.log('  Most are the same measurement under different parameters — which is');
  console.log('  PROTOCOL R1 restated: the pairs are only distinguishable when both');
  console.log('  sides carry their conditions.');
}

if (process.argv.includes('--report')) console.log('\nclassification complete');
