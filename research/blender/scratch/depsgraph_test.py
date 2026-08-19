import bpy, os
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

me = bpy.data.meshes.new("m"); me.from_pydata([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)],[],[(0,1,2,3)]); me.update()
ob = bpy.data.objects.new("Mover", me); sc.collection.objects.link(ob)

# keyframe X from 0 at frame 1 to 10 at frame 50
ob.location = (0,0,0); ob.keyframe_insert("location", frame=1)
ob.location = (10,0,0); ob.keyframe_insert("location", frame=50)

print("=== A. scene.frame_current = N  (direct assignment) ===")
sc.frame_current = 50
print("  frame_current      :", sc.frame_current)
print("  ob.location.x      :", round(ob.location.x,4), "   <- raw RNA (animated by fcurve)")
dg = bpy.context.evaluated_depsgraph_get()
print("  evaluated .x       :", round(ob.evaluated_get(dg).matrix_world.translation.x,4))

print("=== B. scene.frame_set(N) ===")
sc.frame_current = 1
dg = bpy.context.evaluated_depsgraph_get()
print("  after frame_current=1, evaluated .x :", round(ob.evaluated_get(dg).matrix_world.translation.x,4))
sc.frame_set(50)
dg = bpy.context.evaluated_depsgraph_get()
print("  after frame_set(50), evaluated .x   :", round(ob.evaluated_get(dg).matrix_world.translation.x,4))

print()
print("=== C. transform written, matrix_world read WITHOUT update ===")
ob2 = bpy.data.objects.new("T", bpy.data.meshes.new("m2")); sc.collection.objects.link(ob2)
ob2.location = (0,0,0)
bpy.context.view_layer.update()
ob2.location = (7,0,0)
print("  ob2.location       :", tuple(round(v,3) for v in ob2.location))
print("  ob2.matrix_world.tr:", tuple(round(v,3) for v in ob2.matrix_world.translation), " <- STALE?")
bpy.context.view_layer.update()
print("  after view_layer.update():", tuple(round(v,3) for v in ob2.matrix_world.translation))

print()
print("=== D. modifier result read without evaluated_get ===")
me3 = bpy.data.meshes.new("m3"); me3.from_pydata([(-1,-1,0),(1,-1,0),(1,1,0),(-1,1,0)],[],[(0,1,2,3)]); me3.update()
ob3 = bpy.data.objects.new("Sub", me3); sc.collection.objects.link(ob3)
ob3.modifiers.new("Sub","SUBSURF").levels = 3
print("  ob3.data.vertices (raw)      :", len(ob3.data.vertices))
dg = bpy.context.evaluated_depsgraph_get()
print("  evaluated_get().data.vertices:", len(ob3.evaluated_get(dg).data.vertices))

print()
print("=== E. does bpy.ops.render.render() itself flush a pending frame change? ===")
sc.render.resolution_x = sc.render.resolution_y = 32
sc.render.image_settings.file_format='PNG'
sc.frame_current = 1
sc.frame_current = 50            # direct assignment, no frame_set
sc.render.filepath = os.path.join(OUT,"deps_frame50_direct.png")
bpy.ops.render.render(write_still=True)
dg = bpy.context.evaluated_depsgraph_get()
print("  after render, evaluated .x   :", round(ob.evaluated_get(dg).matrix_world.translation.x,4))
