"""Isolate two things the lower third render contradicted:

  1. which side of the clip edge is OPAQUE (static, no animation involved)
  2. whether MATERIAL node-tree animation is evaluated per frame in -b

Renders 3 frames. Nothing else in the scene changes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boyd_gfx as G

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders", "probe_mask")

st = G.Stage(1920, 1080, fps=30, frames=3, samples=16, dither=0.0)

# A: static edge at screen x=600, nothing keyed. Bar spans 200..1400.
a = st.rect(200, 100, 1200, 120, color=G.INK, name="STATIC")
a.set_wipe_x(600)

# B: identical bar, edge KEYED 300 -> 1300 over frames 1..3
b = st.rect(200, 300, 1200, 120, color=G.RED, name="KEYED")
b.set_wipe_x(300)
b.wipe_x([(1, 300), (3, 1300)])

# C: control, no clipping at all
st.rect(200, 500, 1200, 120, color=G.INK, opacity=0.5, name="CTRL")

st.render(OUT)
print("rendered ->", OUT)
