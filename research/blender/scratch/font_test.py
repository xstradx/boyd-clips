import bpy, os, shutil

bpy.ops.wm.read_factory_settings(use_empty=True)

BS = chr(92)  # backslash, avoids any escaping ambiguity


def T(label, fn):
    try:
        r = fn()
        print("  PASS %-58s -> %s" % (label, r))
    except Exception as e:
        print("  FAIL %-58s -> %s: %s" % (label, type(e).__name__, str(e).splitlines()[0][:80]))


A = r"C:\Users\natha\Projects\boyd-clips\assets\fonts\Anton-Regular.ttf"
print("Anton exists:", os.path.exists(A))
print()
print("=== path flavours ===")
T("backslash abs", lambda: bpy.data.fonts.load(A).name)
T("forward-slash abs", lambda: bpy.data.fonts.load(A.replace(BS, "/")).name)
T("double-backslash abs", lambda: bpy.data.fonts.load(A.replace(BS, BS + BS)).name)
T(r"C:\Windows\Fonts\ariblk.ttf", lambda: bpy.data.fonts.load(r"C:\Windows\Fonts\ariblk.ttf").name)
T("BebasNeue", lambda: bpy.data.fonts.load(r"C:\Users\natha\Projects\boyd-clips\assets\fonts\BebasNeue-Regular.ttf").name)
T("nonexistent path", lambda: bpy.data.fonts.load(r"C:\nope\missing.ttf").name)
T("// relative, blend never saved", lambda: bpy.data.fonts.load("//Anton-Regular.ttf").name)

print()
print("=== DUPLICATE datablocks: load the same path 3x ===")
for i in range(3):
    f = bpy.data.fonts.load(A)
    print("   load #%d -> name=%r" % (i + 1, f.name))
print("   font datablocks now:", [f.name for f in bpy.data.fonts])

print()
print("=== check_existing=True ===")
for i in range(2):
    f = bpy.data.fonts.load(A, check_existing=True)
    print("   load #%d -> %r" % (i + 1, f.name))
print("   font datablocks now:", [f.name for f in bpy.data.fonts])

print()
print("=== SILENT FALLBACK: what happens to a text object when the font load fails ===")
cu = bpy.data.curves.new("t", type='FONT')
cu.body = "BOYD"
print("   default cu.font           :", cu.font.name, "| filepath:", repr(cu.font.filepath))
try:
    cu.font = bpy.data.fonts.load(r"C:\nope\missing.ttf")
except Exception as e:
    print("   load raised               :", type(e).__name__)
print("   cu.font AFTER failed load :", cu.font.name, "  <- silently the built-in default")

print()
print("=== unicode + spaces in directory ===")
d = os.path.join(r"C:\Users\natha\AppData\Local\Temp\claude", "f\u00f6nt dir \u00fcnicode")
os.makedirs(d, exist_ok=True)
p = os.path.join(d, "Anton-Regular.ttf")
shutil.copy(A, p)
T("unicode+space dir", lambda: bpy.data.fonts.load(p).name)

print()
print("=== filepath readback ===")
f = bpy.data.fonts.load(A, check_existing=True)
print("   f.filepath     :", repr(f.filepath))
print("   bpy.path.abspath:", repr(bpy.path.abspath(f.filepath)))
print("   exists         :", os.path.exists(bpy.path.abspath(f.filepath)))

print()
print("=== does the loaded font actually change glyph metrics? (proof it is really used) ===")
sc = bpy.context.scene
for label, path in (("BUILT-IN Bfont", None),
                    ("Anton-Regular", A),
                    ("BebasNeue", r"C:\Users\natha\Projects\boyd-clips\assets\fonts\BebasNeue-Regular.ttf"),
                    ("Arial Black", r"C:\Windows\Fonts\ariblk.ttf")):
    c = bpy.data.curves.new("m", type='FONT')
    c.body = "BOYD CLIPS"
    if path:
        c.font = bpy.data.fonts.load(path, check_existing=True)
    o = bpy.data.objects.new("o", c)
    sc.collection.objects.link(o)
    bpy.context.view_layer.update()
    print("   %-16s width = %.4f  (font datablock: %s)" % (label, o.dimensions.x, c.font.name))
