// Shared parsing + the checks PROTOCOL.md requires.
// Every function here is exercised by selftest.mjs against a positive AND a
// negative control before any real file is judged (PROTOCOL R4).
import fs from 'node:fs';

export const FIELDS = ['CLAIM', 'SEVERITY', 'EVIDENCE', 'WHY-IT-MATTERS', 'PROPOSAL', 'COST'];
export const CLAIMS = new Set(['measurement', 'inference', 'reading']);
export const SEVERITIES = new Set(['blocker', 'high', 'medium', 'low']);
const PLACEHOLDER = /^(pending|tbd|n\/a|na|none yet|unknown|-|\.)?$/i;

// A command that could be pasted and re-run. Deliberately narrow: the tools this
// project actually uses. A prose sentence must not satisfy it.
const RUNNABLE = /(ffmpeg|ffprobe|yt-dlp|sqlite3|md5sum|python|node|grep\s|rg\s|git\s+(log|show|status|blame|ls-files)|Get-ScheduledTask|ls\s|find\s)/;

// Parameters: a flag, an assignment, or a signed dB/threshold figure.
// Boundary-anchored: an earlier version matched the "-forms" inside
// "long-forms" and so believed a prose sentence stated parameters.
const PARAMS = /(?:^|[\s(`'"])(--?[a-zA-Z][\w-]*|[a-z_]+=[^\s]+|-?\d+(?:\.\d+)?\s*dB|d=\d)/;

const ALL_KEYS = [...FIELDS, 'CONTROL+', 'CONTROL-', 'RESTS-ON', 'ASSUMES', 'REGION'];
// A field starts a line, is one of the known keys, and is followed by a colon.
// Line-based rather than regex-based: JS has no \Z, and a lookahead meaning
// "next field OR end of block" fails silently at the last field.
// That bug was caught by the selftest, not by me.
const keyOf = line => {
  const m = line.match(/^([A-Z][A-Z+\-]*):(.*)$/);
  return m && ALL_KEYS.includes(m[1]) ? { k: m[1], rest: m[2] } : null;
};

export function parse(text) {
  const out = [];
  for (const block of text.split(/^##\s+/m).slice(1)) {
    const lines = block.split('\n');
    const head = lines[0].trim();
    const id = head.split(':')[0].trim();
    const f = Object.fromEntries(ALL_KEYS.map(k => [k, null]));
    let cur = null, buf = [];
    const flush = () => { if (cur) f[cur] = buf.join('\n').trim(); cur = null; buf = []; };
    for (const line of lines.slice(1)) {
      const hit = keyOf(line);
      if (hit) { flush(); cur = hit.k; buf = [hit.rest]; }
      else if (cur) buf.push(line);
    }
    flush();
    out.push({ id, head, block, f });
  }
  return out;
}

const empty = v => v === null || PLACEHOLDER.test(v.trim());

/** Returns an array of problem strings. Empty array = the finding conforms. */
export function checkFinding(fi, { requireControls = true } = {}) {
  const p = [];
  const tag = fi.id || '(no id)';
  if (!/^F\d+$/.test(fi.id)) p.push(`${tag}: heading must start "F<n>: <claim>"`);
  for (const k of FIELDS) if (empty(fi.f[k])) p.push(`${tag}: ${k} missing or placeholder`);

  const claim = (fi.f.CLAIM || '').toLowerCase().trim();
  if (fi.f.CLAIM && !CLAIMS.has(claim)) p.push(`${tag}: CLAIM "${fi.f.CLAIM}" not measurement|inference|reading`);
  if (fi.f.SEVERITY && !SEVERITIES.has(fi.f.SEVERITY.toLowerCase().trim())) p.push(`${tag}: bad SEVERITY "${fi.f.SEVERITY}"`);

  const ev = fi.f.EVIDENCE || '';
  // R1: a measurement must be re-runnable verbatim, parameters included.
  if (claim === 'measurement') {
    if (!RUNNABLE.test(ev)) p.push(`${tag}: R1 - measurement EVIDENCE has no re-runnable command`);
    if (!PARAMS.test(ev)) p.push(`${tag}: R1 - measurement EVIDENCE states no parameters`);
  }
  // R3: an inference must name its measurement and its bridging assumption.
  if (claim === 'inference') {
    if (empty(fi.f['RESTS-ON'])) p.push(`${tag}: R3 - inference must declare RESTS-ON`);
    if (empty(fi.f.ASSUMES)) p.push(`${tag}: R3 - inference must declare ASSUMES`);
  }
  // R4: a finding ABOUT a checker needs both controls. Deliberately narrow - an
  // earlier version triggered on the word "silencedetect" and demanded controls
  // from every finding that merely used a detection tool.
  const aboutAChecker = /\b(gate|checker|verify_\w+|verif\w*\.(py|mjs)|passes the|fails the|reads as MET|false pass)\b/i;
  if (requireControls && aboutAChecker.test(fi.head + '\n' + ev)) {
    if (empty(fi.f['CONTROL+'])) p.push(`${tag}: R4 - checker-based finding needs CONTROL+ (a case it must pass, and does)`);
    if (empty(fi.f['CONTROL-'])) p.push(`${tag}: R4 - checker-based finding needs CONTROL- (a case it must fail, and does)`);
  }
  // R5: a regional metric must say which region it selected.
  if (claim === 'measurement' && /\b(chroma|region|window|flat|area|silhouette|crop)\b/i.test(ev)) {
    if (empty(fi.f.REGION)) p.push(`${tag}: R5 - regional metric must declare REGION it selected`);
  }
  return p;
}

/** R7: surface pairs of findings from different files that cite the same
 *  artifact and the same quantity with different numbers.
 *
 *  Precision matters more than recall: a noisy conflict list gets ignored,
 *  which is worse than no list. The first real run produced 490 "conflicts" on
 *  STATE.md alone by pairing any number with any filename in the same block.
 *  Two corrections: the unit must be a real unit (a bare "s" de-pluralised to
 *  "" and so matched everything), and the number must sit within `window`
 *  characters of the artifact name so it is plausibly ABOUT it. */
export function crosscheck(files, { window = 140 } = {}) {
  const QTY = /(-?\d[\d,]*(?:\.\d+)?)\s*(spans?|views?|bytes?|rows?|hits?|files?|seconds?|%|px|dB)\b/gi;
  const ART = /\b([A-Za-z0-9_.-]+\.(?:mp4|jpg|png|json|py|md|ps1|db|onnx|ttf))\b/g;
  const norm = u => {
    u = u.toLowerCase();
    return (u === 'seconds' || u === 'second') ? 'sec' : u.replace(/s$/, '');
  };

  const recs = [];
  for (const { name, findings } of files) {
    for (const fi of findings) {
      const text = fi.block;
      const arts = [...text.matchAll(ART)].map(m => ({ a: m[1], i: m.index }));
      const qtys = [...text.matchAll(QTY)].map(m => ({ n: parseFloat(m[1].replace(/,/g, '')), unit: norm(m[2]), i: m.index }));
      for (const A of arts) for (const Q of qtys) {
        const d = Math.abs(A.i - Q.i);
        if (d > window) continue;
        recs.push({ file: name, id: fi.id, art: A.a, n: Q.n, unit: Q.unit, d });
      }
    }
  }
  // Keep only the nearest number per (file, finding, artifact, unit).
  const best = new Map();
  for (const r of recs) {
    const k = [r.file, r.id, r.art, r.unit].join('|');
    if (!best.has(k) || best.get(k).d > r.d) best.set(k, r);
  }
  const kept = [...best.values()];

  const conflicts = [], seen = new Set();
  for (let i = 0; i < kept.length; i++) for (let j = i + 1; j < kept.length; j++) {
    const A = kept[i], B = kept[j];
    if (A.file === B.file || A.art !== B.art || A.unit !== B.unit || A.n === B.n) continue;
    const key = [A.file, A.id, B.file, B.id, A.art, A.unit].join('|');
    if (seen.has(key)) continue;
    seen.add(key);
    conflicts.push({ artifact: A.art, unit: A.unit, a: `${A.file}:${A.id}=${A.n}`, b: `${B.file}:${B.id}=${B.n}` });
  }
  return conflicts;
}

export const readFindings = p => ({ name: p.split(/[\\/]/).pop(), findings: parse(fs.readFileSync(p, 'utf8')) });
