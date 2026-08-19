"""PROBE: does EEVEE object motion blur actually work in this Blender, and how much?

Smallest thing that touches reality and returns a fact. A plane crosses frame at
roughly the speed our sting's fastest element moves (~125 px/frame). Render the
same frame at several shutter values and measure the SMEAR WIDTH in pixels.

If smear width does not grow with shutter, EEVEE object motion blur is not
working here and the whole "add motion blur" fix is dead — better to learn that
from a 6-frame probe than from a full re-render.

Run:  blender -b -P research/blender/probe_mblur.py
"""
import sys
from pathlib import Path

import bpy

OUT = Path(bpy.path.abspath("//")) / "research" / "blender" / "renders" / "probe_mblur"
if not str(OUT).replace("\\", "/").startswith("C:"):
    OUT = Path(r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\probe_mblur")
OUT.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1920, 1080, 60
SPEED_PX = 125.0          # matches the measured peak of the current sting


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def build():
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.fps, sc.render.fps_base = FPS, 1
    sc.render.engine = 'BLENDER_EEVEE'
    sc.frame_start, sc.frame_end = 1, 3

    # flat, unlit, brand-exact — same colour management idiom as the sting
    sc.view_settings.view_transform = 'Standard'
    sc.render.film_transparent = False

    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0, -10, 0)
    cam.rotation_euler = (1.5707963, 0, 0)
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 10.0            # 10 blender units across 1920 px

    # world units per pixel, so we can move exactly SPEED_PX per frame
    upp = 10.0 / W
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    ob = bpy.context.object
    ob.rotation_euler = (1.5707963, 0, 0)
    ob.scale = (0.35, 1.0, 1.2)

    mat = bpy.data.materials.new("flat")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = (0.95, 0.93, 0.89, 1.0)
    em.inputs[1].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs[0])
    ob.data.materials.append(mat)

    # dark ground so smear is measurable against it
    world = bpy.data.worlds.new("w")
    sc.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.03, 0.04, 1)

    # linear travel at exactly SPEED_PX per frame
    for f in (1, 2, 3):
        ob.location = ((f - 2) * SPEED_PX * upp, 0, 0)
        ob.keyframe_insert("location", frame=f)
    # Blender 5.x slotted actions — Action.fcurves is gone (capability doc 2.5)
    ad = ob.animation_data
    for fc in ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves:
        for k in fc.keyframe_points:
            k.interpolation = 'LINEAR'
    return sc


def render_at(sc, shutter, tag):
    r = sc.render
    try:
        r.use_motion_blur = True
        r.motion_blur_shutter = shutter
    except AttributeError as e:
        print(f"  !! motion blur property missing: {e}")
        return None
    sc.frame_set(2)
    ims = sc.render.image_settings
    ims.media_type = 'IMAGE'
    ims.file_format = 'PNG'
    ims.color_mode = 'RGB'
    r.filepath = str(OUT / f"mb_{tag}")
    bpy.ops.render.render(write_still=True)
    return OUT / f"mb_{tag}.png"


def main():
    clear()
    sc = build()

    print("== EEVEE motion blur probe ==")
    print(f"engine: {sc.render.engine}")
    print(f"plane travels {SPEED_PX} px/frame (matches sting peak)")
    have = hasattr(sc.render, "use_motion_blur")
    print(f"render.use_motion_blur exists: {have}")
    if have:
        print(f"  default shutter: {sc.render.motion_blur_shutter}")
    for attr in ("motion_blur_position", "motion_blur_steps"):
        print(f"  {attr}: {getattr(sc.render, attr, 'ABSENT')}")

    made = []
    # shutter 0 == off, 0.5 == 180 degrees, 1.0 == 360 degrees
    for shutter, tag in ((0.0, "off"), (0.5, "180deg"), (1.0, "360deg")):
        p = render_at(sc, shutter, tag)
        if p:
            made.append((tag, shutter, p))
            print(f"  rendered shutter={shutter} -> {p.name}")

    print("\nWROTE:")
    for tag, s, p in made:
        print(f"  {tag}\t{p}")


main()
