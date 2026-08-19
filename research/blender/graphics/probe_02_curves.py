"""Diagnostic: dump the wipe fcurves the lower third actually built, and
evaluate them per frame. No rendering."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boyd_gfx as G
import gfx_lower_third as LT

st, out, f_end = LT.build("MARCUS D. BOYD", "MANSLAUGHTER, SECOND DEGREE",
                          render=False)

for ob in st.sc.objects:
    if ob.type not in ('MESH', 'FONT'):
        continue
    nt = ob.data.materials[0].node_tree if ob.data.materials else None
    if nt is None or nt.animation_data is None:
        continue
    for fc in G._fcurves(nt):
        print("%-10s %s" % (ob.name, fc.data_path))
        print("    keys:", [(round(k.co[0], 1), round(k.co[1], 1)) for k in fc.keyframe_points])
        print("    hR  :", [(k.handle_right_type, round(k.handle_right[0], 1),
                             round(k.handle_right[1], 1)) for k in fc.keyframe_points])
        print("    hL  :", [(k.handle_left_type, round(k.handle_left[0], 1),
                             round(k.handle_left[1], 1)) for k in fc.keyframe_points])
        samp = [(f, round(fc.evaluate(f) + 960.0, 1))
                for f in (1, 5, 8, 10, 12, 15, 17, 40, 60, 100, 119, 122, 125, 128, 131)]
        print("    eval (as screen px):", samp)
        print()
