import bpy, time
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

print("initial engine:", sc.render.engine)
print("enum_items:", [i.identifier for i in sc.render.bl_rna.properties['engine'].enum_items])
sc.render.engine = 'CYCLES'
print("after assign, sc.render.engine =", repr(sc.render.engine))
print("bpy.context.engine =", repr(bpy.context.engine))

# Does the Cycles RenderEngine class exist / is it registered?
engines = [c for c in bpy.types.RenderEngine.__subclasses__()]
print("Registered RenderEngine subclasses:", [(c.bl_idname if hasattr(c,'bl_idname') else c.__name__) for c in engines])

# Cycles-only settings should be reachable
print("scene.cycles.samples:", sc.cycles.samples)

# Build a scene where Cycles and EEVEE MUST differ: a glass/refraction + area light w/ soft shadow
bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,-1))
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0,0,0.2))
bpy.ops.object.light_add(type='AREA', location=(3,-3,5)); bpy.context.object.data.energy=2000
bpy.ops.object.camera_add(location=(0,-7,3), rotation=(1.15,0,0)); sc.camera=bpy.context.object
sc.render.resolution_x, sc.render.resolution_y = 320, 200
sc.render.image_settings.file_format='PNG'

for eng, samples in (('BLENDER_EEVEE',None), ('CYCLES',128)):
    sc.render.engine = eng
    if eng=='CYCLES':
        sc.cycles.samples = samples; sc.cycles.device='CPU'
    sc.render.filepath = rf"C:\Users\natha\Projects\boyd-clips\research\blender\renders\enginecheck_{eng}_"
    t=time.time()
    bpy.ops.render.render(write_still=True)
    print(f"{eng}: engine_reported={sc.render.engine} time={time.time()-t:.2f}s")
