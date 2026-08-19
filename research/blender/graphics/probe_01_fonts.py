"""Font metrics measured from EVALUATED Blender geometry, plus proof that the
static instancing actually changed the letterforms (not just the name table).

Run: blender -b --python probe_01_fonts.py

Writes metrics.json next to this file. Production code reads that instead of
re-measuring, because measuring costs a depsgraph evaluation per string.

The load-bearing question: TextCurve.size is NOT the em square on this build.
Measured cap height at size=100 disagrees with the font's own sCapHeight/upm by
up to 35% (Anton: 0.859 in the font file, 0.554 rendered). Broadcast graphics
are specified by CAP HEIGHT in pixels, so every size in the kit is derived from
the measured ratio, never from the font's declared metrics.
"""
import json
import os

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
DIRS = [r"C:\Users\natha\Projects\boyd-clips\assets\fonts",
        os.path.join(HERE, "fonts_static")]

sc = bpy.context.scene
tc = bpy.data.curves.new("M", type='FONT')
tc.size = 100.0
tc.align_x = 'LEFT'
tc.align_y = 'BOTTOM_BASELINE'
ob = bpy.data.objects.new("M", tc)
sc.collection.objects.link(ob)


def ink(body):
    """(min_x, max_x, min_y, max_y) of the evaluated outline, or None."""
    tc.body = body
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    if not len(me.vertices):
        ev.to_mesh_clear()
        return None
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    r = (min(xs), max(xs), min(ys), max(ys))
    ev.to_mesh_clear()
    return r


out = {}
files = []
for d in DIRS:
    if os.path.isdir(d):
        files += [os.path.join(d, f) for f in sorted(os.listdir(d))
                  if f.lower().endswith((".ttf", ".otf"))]

print("%-34s %-26s %7s %7s %7s %7s %7s" % (
    "file", "blender reports", "cap", "xht", "asc", "desc", "stem"))
for p in files:
    f = bpy.data.fonts.load(p)
    tc.font = f
    H = ink("H")
    x = ink("x")
    d = ink("Hpg")
    I = ink("I")
    if H is None:
        print("%-34s NO GEOMETRY" % os.path.basename(p))
        continue
    cap = H[3]                       # H sits on the baseline: max_y == cap height
    xht = x[3] if x else 0.0
    asc = d[3] if d else cap
    desc = d[2] if d else 0.0
    stem = (I[1] - I[0]) if I else 0.0     # 'I' ink width == the stem weight

    # advance widths for the full charset we actually set (wrapping needs these)
    adv = {}
    base = ink("HH")
    one = ink("H")
    unit = base[1] - one[1]                # advance of 'H'
    for ch in ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
               "abcdefghijklmnopqrstuvwxyz0123456789"
               ".,:;'\"!?()-\u2014\u2013/&%$#*+ "):
        a = ink("H%sH" % ch)
        adv[ch] = round((a[1] - base[1]), 4) if a else unit
    out[os.path.basename(p)] = dict(
        path=p, blender_name=f.name, cap=round(cap, 3), x_height=round(xht, 3),
        ascender=round(asc, 3), descender=round(desc, 3), stem_I=round(stem, 3),
        adv=adv)
    print("%-34s %-26s %7.2f %7.2f %7.2f %7.2f %7.2f" % (
        os.path.basename(p), f.name, cap, xht, asc, desc, stem))

with open(os.path.join(HERE, "metrics.json"), "w") as fh:
    json.dump(out, fh, indent=1)
print("\nwrote metrics.json  (%d faces)" % len(out))

print("\nPROOF the instancing changed LETTERFORMS, not just names")
print("stem width of 'I' at size=100, per face:")
for k in sorted(out, key=lambda k: out[k]["stem_I"]):
    print("   %-34s stem=%6.2f  (%s)" % (k, out[k]["stem_I"], out[k]["blender_name"]))
