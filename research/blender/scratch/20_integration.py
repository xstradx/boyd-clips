"""INTEGRATION: custom easing + motion blur + DOF + compositor grade,
rendered as a frame sequence AND an FFMPEG mp4, all in background mode."""
import bpy, os, sys, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boyd_anim import find_fcurve, cubic_bezier_ease

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\integration"
os.makedirs(OUT, exist_ok=True)
BG, INK, RED = (0.082, 0.094, 0.114, 1), (0.949, 0.933, 0.890, 1), (0.831, 0.169, 0.169, 1)
NF = 24

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x, sc.render.resolution_y = 960, 540
sc.render.fps = 24
sc.frame_start, sc.frame_end = 1, NF
sc.eevee.taa_render_samples = 32
sc.eevee.motion_blur_steps = 8
sc.render.use_motion_blur = True
sc.render.motion_blur_shutter = 0.5

w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = BG
bpy.ops.object.light_add(type='AREA', location=(5, -6, 7)); bpy.context.object.data.energy = 4000

def mat(name, base, emis=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = base
    b.inputs["Roughness"].default_value = 0.35
    b.inputs["Emission Color"].default_value = base
    b.inputs["Emission Strength"].default_value = emis
    return m

# hero object: flies in with a custom ease-out + slight overshoot
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.1, location=(0, 0, 0))
hero = bpy.context.object
bpy.ops.object.shade_smooth()
hero.data.materials.append(mat("hero", RED, 3.0))
hero.location = (-14, 0, 0); hero.keyframe_insert("location", frame=1)
hero.location = (0, 0, 0);   hero.keyframe_insert("location", frame=NF)
fcx = find_fcurve(hero, "location", 0)
cubic_bezier_ease(fcx, 0, (0.05, 1.12), (0.35, 1.0))   # snap in, slight overshoot
hero.rotation_euler = (0, 0, 0);      hero.keyframe_insert("rotation_euler", frame=1)
hero.rotation_euler = (0, 0, 2.2);    hero.keyframe_insert("rotation_euler", frame=NF)
for i in (0, 1, 2):
    fr = find_fcurve(hero, "rotation_euler", i)
    if fr:
        for kp in fr.keyframe_points:
            kp.interpolation, kp.easing = 'QUINT', 'EASE_OUT'
        fr.update()

# background slabs at varying depth for DOF to bite on
for i in range(6):
    bpy.ops.mesh.primitive_cube_add(size=1.4, location=(-5 + i*2.1, 5 + i*2.4, -0.6))
    bpy.context.object.data.materials.append(mat(f"bg{i}", INK if i % 2 else RED))

bpy.ops.object.camera_add(location=(0, -11, 1.6), rotation=(1.48, 0, 0))
cam = bpy.context.object; sc.camera = cam
cam.data.lens = 55
cam.data.dof.use_dof = True
cam.data.dof.focus_object = hero
cam.data.dof.aperture_fstop = 1.2
cam.data.dof.aperture_blades = 6
# subtle handheld shake via NOISE F-Modifier
cam.rotation_euler = (1.48, 0, 0); cam.keyframe_insert("rotation_euler", frame=1)
cam.rotation_euler = (1.48, 0, 0); cam.keyframe_insert("rotation_euler", frame=NF)
for i in (0, 2):
    fc = find_fcurve(cam, "rotation_euler", i)
    nm = fc.modifiers.new(type='NOISE')
    nm.scale, nm.strength, nm.phase, nm.depth = 8.0, 0.012, i * 7.0, 2
    fc.update()

# compositor grade
def sock(n, name, t): return [s for s in n.inputs if s.name == name and s.type == t][0]
def by_id(n, i): return [s for s in n.inputs if s.identifier == i][0]

ng = bpy.data.node_groups.new("Grade", "CompositorNodeTree")
sc.compositing_node_group = ng
ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
N, L = ng.nodes, ng.links
rl = N.new("CompositorNodeRLayers"); rl.scene = sc
gl = N.new("CompositorNodeGlare")
gl.inputs["Type"].default_value = 'Bloom'
gl.inputs["Quality"].default_value = 'High'
gl.inputs["Threshold"].default_value = 0.85
gl.inputs["Strength"].default_value = 0.35
gl.inputs["Size"].default_value = 0.5
ld = N.new("CompositorNodeLensdist")
ld.inputs["Type"].default_value = 'Radial'
ld.inputs["Dispersion"].default_value = 0.12
ld.inputs["Fit"].default_value = True
cb = N.new("CompositorNodeColorBalance")
cb.inputs["Type"].default_value = 'Lift/Gamma/Gain'
sock(cb, "Lift", 'RGBA').default_value = (0.02, 0.03, 0.06, 1.0)
sock(cb, "Gain", 'RGBA').default_value = (1.06, 1.0, 0.95, 1.0)
el = N.new("CompositorNodeEllipseMask"); el.inputs["Size"].default_value = (0.78, 0.85)
bl = N.new("CompositorNodeBlur")
bl.inputs["Type"].default_value = 'Fast Gaussian'; bl.inputs["Size"].default_value = (0.25, 0.25)
mx = N.new("ShaderNodeMix"); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'
by_id(mx, 'Factor_Float').default_value = 0.55
go = N.new("NodeGroupOutput")
L.new(rl.outputs["Image"], gl.inputs["Image"]); L.new(gl.outputs["Image"], ld.inputs["Image"])
L.new(ld.outputs["Image"], cb.inputs["Image"]); L.new(cb.outputs["Image"], by_id(mx, 'A_Color'))
L.new(el.outputs["Mask"], bl.inputs["Image"]); L.new(bl.outputs["Image"], by_id(mx, 'B_Color'))
L.new(mx.outputs["Result"], go.inputs["Image"])

# ---- PNG sequence ----
seq = os.path.join(OUT, "seq"); os.makedirs(seq, exist_ok=True)
for f in os.listdir(seq): os.remove(os.path.join(seq, f))
sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = os.path.join(seq, "i_")
bpy.ops.render.render(animation=True)

files = sorted(os.listdir(seq))
hs = [hashlib.sha256(open(os.path.join(seq, f), 'rb').read()).hexdigest()[:10] for f in files]
print(f"\nPNG seq: {len(files)} frames, {len(set(hs))} unique -> "
      f"{'PASS' if len(set(hs))==len(files) else 'FAIL'}")

# ---- FFMPEG mp4 ----
im = sc.render.image_settings
print("\nfile_format enum:", [i.identifier for i in im.bl_rna.properties['file_format'].enum_items])
# Blender 5.0: must switch media_type to VIDEO before FFMPEG is a legal file_format
im.media_type = 'VIDEO'
im.file_format = 'FFMPEG'
ff = sc.render.ffmpeg
print("ffmpeg format enum:", [i.identifier for i in ff.bl_rna.properties['format'].enum_items])
print("ffmpeg codec enum:", [i.identifier for i in ff.bl_rna.properties['codec'].enum_items])
ff.format = 'MPEG4'
ff.codec = 'H264'
ff.constant_rate_factor = 'HIGH'
ff.ffmpeg_preset = 'GOOD'
ff.gopsize = 12
sc.render.filepath = os.path.join(OUT, "integration_clip")
bpy.ops.render.render(animation=True)
for f in os.listdir(OUT):
    p = os.path.join(OUT, f)
    if os.path.isfile(p):
        print(f"  OUT {f}  {os.path.getsize(p)} bytes")
