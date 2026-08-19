import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
r = sc.render

print("ENGINES:", [i.identifier for i in r.bl_rna.properties['engine'].enum_items])

# Motion blur props on render
mb = [p.identifier for p in r.bl_rna.properties if 'motion_blur' in p.identifier]
print("render.motion_blur* :", mb)
for p in mb:
    print("   ", p, "=", getattr(r, p))
print("motion_blur_position enum:", [i.identifier for i in r.bl_rna.properties['motion_blur_position'].enum_items] if 'motion_blur_position' in r.bl_rna.properties else 'N/A')

# EEVEE
ee = sc.eevee
print("\nEEVEE struct:", ee.bl_rna.identifier)
props = [p.identifier for p in ee.bl_rna.properties if p.identifier != 'rna_type']
print("EEVEE props:", props)
print("EEVEE bloom-ish:", [p for p in props if 'bloom' in p.lower()])
print("EEVEE motion blur-ish:", [p for p in props if 'motion' in p.lower()])

# Cycles
r.engine = 'CYCLES'
print("\nCycles present:", hasattr(sc, 'cycles'))
if hasattr(sc, 'cycles'):
    cp = [p.identifier for p in sc.cycles.bl_rna.properties if p.identifier != 'rna_type']
    print("cycles motion blur-ish:", [p for p in cp if 'motion' in p.lower() or 'blur' in p.lower()])
    print("cycles device:", [i.identifier for i in sc.cycles.bl_rna.properties['device'].enum_items])

# Camera DOF
bpy.ops.object.camera_add()
cam = bpy.context.object.data
print("\nCamera DOF struct:", cam.dof.bl_rna.identifier)
print("dof props:", [p.identifier for p in cam.dof.bl_rna.properties if p.identifier != 'rna_type'])

# Compositor
sc.use_nodes = True
print("\nscene.use_nodes ok, node_tree:", sc.node_tree)
print("compositor_device:", [i.identifier for i in sc.bl_rna.properties['compositor_device'].enum_items] if 'compositor_device' in sc.bl_rna.properties else 'N/A')
