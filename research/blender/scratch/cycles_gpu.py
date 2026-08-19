import bpy, time, sys, os

mode = sys.argv[-1]
OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.render.resolution_x = sc.render.resolution_y = 900
sc.cycles.samples = 1500
sc.cycles.use_denoising = False
sc.view_settings.view_transform = 'Standard'
sc.render.image_settings.file_format = 'PNG'

cp = bpy.context.preferences.addons['cycles'].preferences

if mode == 'naive':
    # what an AI writes: "use the GPU"
    sc.cycles.device = 'GPU'
elif mode == 'correct':
    cp.compute_device_type = 'OPTIX'
    cp.get_devices()
    for d in cp.devices:
        d.use = (d.type == 'OPTIX')
    sc.cycles.device = 'GPU'
elif mode == 'cpu':
    sc.cycles.device = 'CPU'

print("mode=%-8s scene.cycles.device=%-4s prefs.compute_device_type=%r"
      % (mode, sc.cycles.device, cp.compute_device_type))
print("   enabled devices:", [(d.name[:28], d.type) for d in cp.devices if d.use])

# scene with something to trace
cd = bpy.data.cameras.new("C")
cam = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(cam)
cam.location = (7, -7, 5); cam.rotation_euler = (1.1, 0, 0.78); sc.camera = cam
for i in range(6):
    for j in range(6):
        m = bpy.data.meshes.new("s")
        import mathutils
        bpy.ops.mesh.primitive_uv_sphere_add(location=(i - 2.5, j - 2.5, 0), radius=0.45)
lt = bpy.data.lights.new("L", 'AREA'); lt.energy = 2000; lt.size = 8
lo = bpy.data.objects.new("L", lt); sc.collection.objects.link(lo); lo.location = (0, 0, 9)

sc.render.filepath = os.path.join(OUT, "cyc_%s.png" % mode)
t = time.time()
bpy.ops.render.render(write_still=True)
print("   RENDER TIME: %.2f s" % (time.time() - t))
