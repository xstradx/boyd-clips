"""Look at what the current rubric actually said, and how the two scales compare."""
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
    W = {'pushback': 30, 'boyd_register': 25, 'receipt': 20,
         'consequence': 15, 'hook_strength': 10}
    for k, v in dims.items():
        print('    %-16s[%2d]  median %5.1f  max %5.1f' % (
            k, W.get(k, 0), st.median(v), max(v)))
print('\n  top 3, with the model\'s own reasoning:')
for r in sorted(rows, key=lambda r: -r['total_score'])[:3]:
    print('\n== %s  %.1f -> %.1f' % (r['case_key'], r['old_score'] or 0, r['total_score']))
    for k, v in json.loads(r['scores_json']).items():
        print('   %-15s %3s  %s' % (k, v.get('score'), str(v.get('justification'))[:150]))
