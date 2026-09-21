"""
LEGACY — 2026-08-18 repeat-shortlist workflow. NOT on the daily path and not
the current scoring definition. The live editorial layer is BOYD_EDITORIAL_V2
(src/boydclips/editorial.py, prompts/score_cases.md); use tools/editorial_eval.py
to re-score stored cases and `tools/banger_digest.py --editorial` on the manual
path. Rows in the `rescores` table are keyed by rubric_version, so anything this
workflow stored under the retired rubric is ignored under the current version.

Look at what the current rubric actually said, and how the two scales compare."""
import sys as _sys
_sys.stderr.write('[LEGACY] ' + __doc__.strip().splitlines()[0] + ' -- see the module docstring\n')

import sqlite3, json, statistics as st
c = sqlite3.connect('state/pipeline.db'); c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute(
    'select case_key, old_score, total_score, eligible, scores_json from rescores')]
print('%d re-scored, %d eligible on the current gate' % (
    len(rows), sum(r['eligible'] for r in rows)))
if rows:
    new = [r['total_score'] for r in rows]
    old = [r['old_score'] or 0 for r in rows]
    print('  old rubric: median %5.1f  max %5.1f' % (st.median(old), max(old)))
    print('  new rubric: median %5.1f  max %5.1f' % (st.median(new), max(new)))
    dims = {}
    for r in rows:
        for k, v in json.loads(r['scores_json']).items():
            dims.setdefault(k, []).append(v.get('score') or 0)
    print('\n  per-dimension medians (weight in brackets):')
    import sys as _s; _s.path.insert(0, 'src')
    from boydclips.editorial import DIMENSIONS as W   # BOYD_EDITORIAL_V2 maxima
    for k, v in dims.items():
        print('    %-16s[%2d]  median %5.1f  max %5.1f' % (
            k, W.get(k, 0), st.median(v), max(v)))
print('\n  top 3, with the model\'s own reasoning:')
for r in sorted(rows, key=lambda r: -r['total_score'])[:3]:
    print('\n== %s  %.1f -> %.1f' % (r['case_key'], r['old_score'] or 0, r['total_score']))
    for k, v in json.loads(r['scores_json']).items():
        print('   %-15s %3s  %s' % (k, v.get('score'), str(v.get('justification'))[:150]))
