import bpy, os
vs = bpy.context.scene.view_settings
prop = vs.bl_rna.properties['view_transform']
print("enum_items      :", [i.identifier for i in prop.enum_items])
print("enum_items_static:", [i.identifier for i in prop.enum_items_static])
print("is_enum_flag:", prop.is_enum_flag)
print()
# brute-force: try assigning known names, see which stick
cands = ["Standard","Raw","Filmic","Filmic Log","AgX","AgX Log","False Color",
         "Khronos PBR Neutral","ACES 1.0 - SDR Video","Display P3","Rec.1886","None"]
for c in cands:
    try:
        vs.view_transform = c
        print(f"  OK   {c!r:28} -> now {vs.view_transform!r}")
    except Exception as e:
        print(f"  FAIL {c!r:28} -> {type(e).__name__}: {str(e)[:90]}")
vs.view_transform = 'AgX'
print()
looks = ["None","AgX - Punchy","AgX - Base Contrast","AgX - Medium High Contrast",
         "Punchy","Medium High Contrast","Very High Contrast","Base Contrast"]
for c in looks:
    try:
        vs.look = c
        print(f"  LOOK OK   {c!r:32} -> {vs.look!r}")
    except Exception as e:
        print(f"  LOOK FAIL {c!r:32} -> {str(e)[:80]}")
print()
print("OCIO env:", os.environ.get("OCIO","<unset>"))
import bpy.utils
p = os.path.join(os.path.dirname(bpy.app.binary_path), "5.0", "datafiles", "colormanagement", "config.ocio")
print("config exists:", p, os.path.exists(p))
