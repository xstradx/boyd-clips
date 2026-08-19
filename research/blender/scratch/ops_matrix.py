import bpy, traceback
bpy.ops.wm.read_factory_settings(use_empty=False)   # default cube scene
sc = bpy.context.scene
print("background mode:", bpy.app.background)
print("context.window :", bpy.context.window)
print("context.screen :", bpy.context.screen)
print("context.area   :", bpy.context.area)
print("wm.windows     :", len(bpy.data.window_managers[0].windows))
print("screens in file:", [s.name for s in bpy.data.screens])
print()
def T(label, fn):
    try:
        r = fn()
        print(f"  PASS  {label:52} -> {r}")
    except Exception as e:
        print(f"  FAIL  {label:52} -> {type(e).__name__}: {str(e).splitlines()[0][:110]}")

cube = bpy.data.objects.get("Cube")
if cube:
    bpy.context.view_layer.objects.active = cube
    cube.select_set(True)

print("=== object/mesh ops in -b ===")
T("bpy.ops.mesh.primitive_cube_add()",        lambda: bpy.ops.mesh.primitive_cube_add())
T("bpy.ops.object.select_all(action='SELECT')",lambda: bpy.ops.object.select_all(action='SELECT'))
T("bpy.ops.object.mode_set(mode='EDIT')",     lambda: bpy.ops.object.mode_set(mode='EDIT'))
T("bpy.ops.object.mode_set(mode='OBJECT')",   lambda: bpy.ops.object.mode_set(mode='OBJECT'))
T("bpy.ops.object.shade_smooth()",            lambda: bpy.ops.object.shade_smooth())
T("bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')", lambda: bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY'))
T("bpy.ops.object.transform_apply(scale=True)",lambda: bpy.ops.object.transform_apply(location=False,rotation=False,scale=True))
T("bpy.ops.object.duplicate()",               lambda: bpy.ops.object.duplicate())
T("bpy.ops.object.join()",                    lambda: bpy.ops.object.join())
T("bpy.ops.object.text_add()",                lambda: bpy.ops.object.text_add())
T("bpy.ops.object.convert(target='MESH')",    lambda: bpy.ops.object.convert(target='MESH'))
T("bpy.ops.transform.translate(value=(1,0,0))",lambda: bpy.ops.transform.translate(value=(1,0,0)))
T("bpy.ops.object.modifier_add(type='SUBSURF')",lambda: bpy.ops.object.modifier_add(type='SUBSURF'))
print()
print("=== UI-space ops in -b ===")
T("bpy.ops.view3d.camera_to_view()",          lambda: bpy.ops.view3d.camera_to_view())
T("bpy.ops.view3d.snap_cursor_to_center()",   lambda: bpy.ops.view3d.snap_cursor_to_center())
T("bpy.ops.screen.frame_jump(end=True)",      lambda: bpy.ops.screen.frame_jump(end=True))
T("bpy.ops.screen.animation_play()",          lambda: bpy.ops.screen.animation_play())
T("bpy.ops.node.select_all(action='SELECT')", lambda: bpy.ops.node.select_all(action='SELECT'))
T("bpy.ops.font.text_insert(text='X')",       lambda: bpy.ops.font.text_insert(text='X'))
T("bpy.ops.image.open(filepath='x.png')",     lambda: bpy.ops.image.open(filepath='x.png'))
T("bpy.ops.render.opengl()",                  lambda: bpy.ops.render.opengl())
T("bpy.ops.wm.obj_export(filepath='C:/Users/natha/AppData/Local/Temp/claude/t.obj')", lambda: bpy.ops.wm.obj_export(filepath='C:/Users/natha/AppData/Local/Temp/claude/t.obj'))
print()
print("=== temp_override availability (the 5.x idiom) ===")
print("  hasattr(bpy.context,'temp_override'):", hasattr(bpy.context,'temp_override'))
try:
    with bpy.context.temp_override(scene=sc):
        print("  temp_override(scene=...) works in -b: OK")
except Exception as e:
    print("  temp_override FAILED:", e)
# try to fabricate a VIEW_3D area in background
print("  any window_manager windows to override with:", len(bpy.context.window_manager.windows))
