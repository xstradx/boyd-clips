// PROTOCOL R4: the checkers prove themselves against a known-pass and a
// known-fail case before they are trusted on real data. If this file exits
// non-zero, nothing downstream may be believed.
import { parse, checkFinding, crosscheck } from './lib.mjs';

let failures = 0;
const t = (name, cond, detail = '') => {
  if (cond) console.log(`  ok    ${name}`);
  else { console.error(`  FAIL  ${name} ${detail}`); failures++; }
};

// ---------------------------------------------------------------- fixtures
const GOOD = `
## F1: CARTHIEF_LONGFORM has no silence over 4s at the project's own threshold
CLAIM: measurement
SEVERITY: low
EVIDENCE: ffmpeg -i CARTHIEF_LONGFORM.mp4 -af silencedetect=noise=-30dB:d=4.0 -f null - | grep -c silence_start -> 0 spans
WHY-IT-MATTERS: element 2 passes its literal test
PROPOSAL: NONE
COST: none
`;
const NO_COMMAND = `
## F1: the pipeline looks unreliable to me
CLAIM: measurement
SEVERITY: high
EVIDENCE: reading through the render path it is clear that assets are treated as optional throughout
WHY-IT-MATTERS: prose is not a measurement
PROPOSAL: NONE
COST: none
`;
const NO_PARAMS = `
## F1: the long-forms have no dead air
CLAIM: measurement
SEVERITY: high
EVIDENCE: ran ffmpeg silencedetect over the long-forms and it returned zero spans every time
WHY-IT-MATTERS: this is the exact shape of the claim that was wrong
PROPOSAL: NONE
COST: none
`;
const BARE_INFERENCE = `
## F1: the shipped thumbnails are the variants Nathan rejected
CLAIM: inference
SEVERITY: blocker
EVIDENCE: md5sum CARTHIEF_thumbnail.jpg AB-THUMBNAILS/CARTHIEF_thumb_A.jpg -> identical hashes
WHY-IT-MATTERS: a rejected variant may have shipped
PROPOSAL: re-check the picks
COST: low
`;
const CHECKER_NO_CONTROLS = `
## F1: the severed-limb gate does not detect a severed limb
CLAIM: measurement
SEVERITY: blocker
EVIDENCE: node verify_set.py --limb CARTHIEF_thumbnail.jpg -> no LIMB failure, threshold 0.55
WHY-IT-MATTERS: the gate reads as MET on a known-bad file
PROPOSAL: replace the metric
COST: low
`;

// ---------------------------------------------------------- finding checker
console.log('findings checker:');
t('accepts a complete measurement', checkFinding(parse(GOOD)[0]).length === 0,
  JSON.stringify(checkFinding(parse(GOOD)[0])));

const p0 = checkFinding(parse(NO_COMMAND)[0]);
t('R1 rejects a measurement that is prose, not a command', p0.some(x => x.includes('re-runnable')));
const p1 = checkFinding(parse(NO_PARAMS)[0]);
t('R1 rejects a measurement naming a tool but no parameters', p1.some(x => x.includes('no parameters')),
  JSON.stringify(p1));

const p2 = checkFinding(parse(BARE_INFERENCE)[0]);
t('R3 rejects an inference with no RESTS-ON', p2.some(x => x.includes('RESTS-ON')));
t('R3 rejects an inference with no ASSUMES', p2.some(x => x.includes('ASSUMES')));

const p3 = checkFinding(parse(CHECKER_NO_CONTROLS)[0]);
t('R4 rejects a checker finding with no CONTROL+', p3.some(x => x.includes('CONTROL+')));
t('R4 rejects a checker finding with no CONTROL-', p3.some(x => x.includes('CONTROL-')));

// ------------------------------------------------------------- crosscheck
if (process.argv.includes('--crosscheck')) {
  console.log('\ncrosscheck detector:');
  // POSITIVE CONTROL: the real dead-air contradiction, reduced to its shape.
  const A = { name: 'leaf-1.3.md', findings: parse(`
## F1: dead air is clean
CLAIM: measurement
SEVERITY: low
EVIDENCE: silencedetect on CARTHIEF_LONGFORM.mp4 returned 0 spans
WHY-IT-MATTERS: x
PROPOSAL: NONE
COST: none
`) };
  const B = { name: 'leaf-4.1.md', findings: parse(`
## F1: dead air is not clean
CLAIM: measurement
SEVERITY: high
EVIDENCE: silencedetect on CARTHIEF_LONGFORM.mp4 returned 23 spans
WHY-IT-MATTERS: x
PROPOSAL: NONE
COST: none
`) };
  const hit = crosscheck([A, B]);
  t('detects the known dead-air conflict', hit.some(c => c.artifact === 'CARTHIEF_LONGFORM.mp4' && c.unit === 'span'),
    JSON.stringify(hit));

  // NEGATIVE CONTROL: same artifact, same unit, same number -> must stay silent.
  const C = { name: 'leaf-9.9.md', findings: parse(`
## F1: dead air is clean, agreeing
CLAIM: measurement
SEVERITY: low
EVIDENCE: silencedetect on CARTHIEF_LONGFORM.mp4 returned 0 spans
WHY-IT-MATTERS: x
PROPOSAL: NONE
COST: none
`) };
  const quiet = crosscheck([A, C]);
  t('stays silent when two findings agree', quiet.length === 0, JSON.stringify(quiet));

  // NEGATIVE CONTROL 2: different artifacts must never be compared.
  const D = { name: 'leaf-8.8.md', findings: parse(`
## F1: a different file entirely
CLAIM: measurement
SEVERITY: low
EVIDENCE: silencedetect on MONKEY_LONGFORM.mp4 returned 23 spans
WHY-IT-MATTERS: x
PROPOSAL: NONE
COST: none
`) };
  t('does not compare different artifacts', crosscheck([A, D]).length === 0);

  console.log(failures ? `\n${failures} selftest failure(s)` : '\ncrosscheck selftest passed');
  process.exit(failures ? 1 : 0);
}

console.log(failures ? `\n${failures} selftest failure(s)` : '\nselftest passed');
process.exit(failures ? 1 : 0);
