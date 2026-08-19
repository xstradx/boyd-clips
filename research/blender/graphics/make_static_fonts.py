"""Blender 5.0 cannot set a variable-font axis. Instance the VFs to static TTFs.

WHY THIS EXISTS (measured, do not delete):
  bpy.types.VectorFont has NO axis/variation/weight property. Neither does
  TextCurve. TextCharacterFormat exposes only use_bold/use_italic/use_small_caps,
  which switch to a SEPARATE font datablock (tc.font_bold), they do not drive an
  fvar axis. So bpy.data.fonts.load() on a variable font silently gives you the
  font's DEFAULT named instance and there is no way to move off it:

      Archivo-Var.ttf    fvar wght 100..900 default 600  -> Blender: "Archivo SemiBold"
      Montserrat-Var.ttf fvar wght 100..900 default 100  -> Blender: "Montserrat Thin"
      Oswald-Var.ttf     fvar wght 200..700 default 400  -> Blender: "Oswald Regular"

  Montserrat at Thin is a hairline. Using it for a lower third at broadcast size
  would be a silent substitution of the worst kind - it renders, it looks
  deliberate, and it is wrong.

Run: python make_static_fonts.py
"""
import os

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

SRC = r"C:\Users\natha\Projects\boyd-clips\assets\fonts"
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts_static")

# weight, and for Archivo also a width axis. Chosen for FUNCTION, not taste:
# a lower third needs one heavy display face and one condensed-ish workhorse
# that stays legible at 26-34 px cap height over moving footage.
WANT = [
    ("Archivo-Var.ttf",    {"wght": 400, "wdth": 100}, "Archivo-Regular.ttf"),
    ("Archivo-Var.ttf",    {"wght": 500, "wdth": 100}, "Archivo-Medium.ttf"),
    ("Archivo-Var.ttf",    {"wght": 700, "wdth": 100}, "Archivo-Bold.ttf"),
    ("Archivo-Var.ttf",    {"wght": 600, "wdth": 87},  "Archivo-SemiCond-SemiBold.ttf"),
    ("Montserrat-Var.ttf", {"wght": 500},              "Montserrat-Medium.ttf"),
    ("Montserrat-Var.ttf", {"wght": 700},              "Montserrat-Bold.ttf"),
    ("Oswald-Var.ttf",     {"wght": 400},              "Oswald-Regular.ttf"),
    ("Oswald-Var.ttf",     {"wght": 500},              "Oswald-Medium.ttf"),
    ("Oswald-Var.ttf",     {"wght": 700},              "Oswald-Bold.ttf"),
]


def main():
    os.makedirs(DST, exist_ok=True)
    for src, loc, out in WANT:
        f = TTFont(os.path.join(SRC, src))
        # updateFontNames=True raises "Cannot find Axis Values {'wdth': 87}" -
        # the STAT table has no Axis Value record for an off-ramp width. Rewrite
        # the name records by hand instead; that also guarantees a UNIQUE family
        # name per instance, which is how we verify inside Blender that the
        # instancing actually took.
        inst = instancer.instantiateVariableFont(f, loc, inplace=False,
                                                 updateFontNames=False)
        fam, sub = out[:-4].rsplit("-", 1) if "-" in out[:-4] else (out[:-4], "Regular")
        fam = fam.replace("-", " ")
        nt = inst["name"]
        for nid, val in ((1, fam), (2, sub), (4, "%s %s" % (fam, sub)),
                         (6, out[:-4].replace("-", "")), (16, fam), (17, sub)):
            nt.setName(val, nid, 3, 1, 0x409)
            nt.setName(val, nid, 1, 0, 0)
        p = os.path.join(DST, out)
        inst.save(p)
        n = inst["name"]
        print("%-32s -> %-30s  family=%r sub=%r  has_fvar=%s" % (
            src, out, n.getDebugName(1), n.getDebugName(2), "fvar" in inst))


if __name__ == "__main__":
    main()
