import bpy
print("=== areas available in -b ? ===")
for s in bpy.data.screens:
    print(f"  screen {s.name:16} areas={len(s.areas)}")
print("  context.area:", bpy.context.area, " context.region:", bpy.context.region)
print("  window.screen areas:", len(bpy.context.window.screen.areas))
print()
print("=== can temp_override rescue a view3d op? ===")
found=None
for s in bpy.data.screens:
    for a in s.areas:
        if a.type=='VIEW_3D': found=(s,a)
print("  VIEW_3D area found:", found)
try:
    with bpy.context.temp_override(area=None):
        bpy.ops.view3d.snap_cursor_to_center()
    print("  override(area=None) -> worked?!")
except Exception as e:
    print("  override(area=None) ->", str(e).splitlines()[0][:100])
print()
print("=== gpu module / offscreen in background ===")
try:
    import gpu
    print("  gpu imported. backend:", gpu.platform.backend_type_get())
    print("  renderer:", gpu.platform.renderer_get())
    off = gpu.types.GPUOffScreen(64,64)
    print("  GPUOffScreen(64,64) CREATED ->", off)
    off.free()
except Exception as e:
    import traceback; print("  gpu FAILED:", type(e).__name__, str(e)[:160])
print()
print("=== other GUI-only surfaces ===")
def T(l,f):
    try: print(f"  PASS {l:44} -> {f()}")
    except Exception as e: print(f"  FAIL {l:44} -> {str(e).splitlines()[0][:100]}")
T("bpy.ops.render.opengl()",         lambda: bpy.ops.render.opengl())
T("bpy.ops.render.view_show()",      lambda: bpy.ops.render.view_show())
T("bpy.ops.wm.window_new()",         lambda: bpy.ops.wm.window_new())
T("bpy.ops.screen.screenshot(filepath='C:/Users/natha/AppData/Local/Temp/claude/ss.png')", lambda: bpy.ops.screen.screenshot(filepath='C:/Users/natha/AppData/Local/Temp/claude/ss.png'))
T("bpy.ops.sequencer.rendersize()",  lambda: bpy.ops.sequencer.rendersize())
T("bpy.ops.preferences.addon_enable(module='io_scene_gltf2')", lambda: bpy.ops.preferences.addon_enable(module='io_scene_gltf2'))
