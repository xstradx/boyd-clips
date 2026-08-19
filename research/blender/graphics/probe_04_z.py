"""Direct test of BOTH z clip directions and the band, at known static edges."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boyd_gfx as G
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders", "probe_z")
st = G.Stage(1920, 1080, fps=30, frames=1, samples=16, dither=0.0)
# A: full-height bar, lower edge at y=400 -> expect opaque ONLY y<=400
a = st.rect(100, 100, 200, 600, color=G.INK, name="ZLO"); a.set_wipe_z(400)
# B: same, upper edge at y=400 -> expect opaque ONLY y>=400
b = st.rect(400, 100, 200, 600, color=G.INK, name="ZHI")
b._cz2.inputs[1].default_value = st.wy(400)
# C: band 300..500
c = st.rect(700, 100, 200, 600, color=G.INK, name="BAND"); c.band(300, 500)
# D: control, unclipped
st.rect(1000, 100, 200, 600, color=G.INK, name="CTRL")
st.render(OUT)
