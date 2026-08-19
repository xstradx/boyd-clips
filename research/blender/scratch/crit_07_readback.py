
# CRITIC TEST 7: the verification METHOD both recon agents used for nearly every
# visual claim -- bpy.data.images.load(p).pixels -- is not a neutral pixel reader.
# What it returns depends on the file's BIT DEPTH (byte buffer vs float buffer)
# and on ALPHA (it associates/premultiplies). Same file content -> different numbers.
import bpy, os, numpy as np
D = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\critic"

def probe(p, label, force_cs=None):
    im = bpy.data.images.load(p, check_existing=False)
    if force_cs:
        im.colorspace_settings.name = force_cs
    a = np.empty(im.size[0]*im.size[1]*4, dtype=np.float32); im.pixels.foreach_get(a)
    c = a.reshape(im.size[1], im.size[0], 4)[im.size[1]//2, im.size[0]//2]
    print("  %-34s is_float=%-5s depth=%-3s cs=%-9s -> pixels=(%.4f,%.4f,%.4f)  x255=(%d,%d,%d)"
          % (label, im.is_float, im.depth, im.colorspace_settings.name,
             c[0], c[1], c[2], round(c[0]*255), round(c[1]*255), round(c[2]*255)))
    bpy.data.images.remove(im)

print("Externally (ffmpeg) BOTH of these files are #15181D at every pixel.")
print("What Blender's own reader reports:")
probe(os.path.join(D, "dith_8_0.0.png"),  "8-bit PNG, default cs")
probe(os.path.join(D, "dith_16_0.0.png"), "16-bit PNG, default cs")
print("\nSame two files, colorspace forced to Non-Color (neutral read):")
probe(os.path.join(D, "dith_8_0.0.png"),  "8-bit PNG, Non-Color",  force_cs='Non-Color')
probe(os.path.join(D, "dith_16_0.0.png"), "16-bit PNG, Non-Color", force_cs='Non-Color')

print("\n0x15=21/255=%.6f (sRGB-encoded) ; its linear value = %.6f" %
      (21/255, ((21/255 + 0.055)/1.055)**2.4))
print("-> the 8-bit read returns the sRGB-ENCODED byte; the 16-bit read returns the LINEARISED value.")
print("-> a threshold/metric tuned on 8-bit PNGs is off by ~11x on 16-bit PNGs of identical content.")

print("\nAlpha association (external ffmpeg on premul.png said R=255 A=128 => STRAIGHT):")
probe(os.path.join(D, "premul.png"), "premul.png as Blender reads it")
print("-> Blender's reader PREMULTIPLIES on load, so a straight-alpha file reads back")
print("   looking premultiplied. You cannot determine alpha association this way.")
