import bpy, os, traceback
LOGO = r"D:\Boyd Clips\boyd-brand\logo_transparent.png"
d, f = os.path.split(LOGO)

def attempt(label, **kw):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.data.objects.keys())
    print("\n---", label, "---")
    try:
        r = bpy.ops.image.import_as_mesh_planes(**kw)
        print("  returned:", r)
        new = set(bpy.data.objects.keys()) - before
        print("  NEW OBJECTS:", new)
        for n in new:
            o = bpy.data.objects[n]
            bpy.context.view_layer.update()
            print("   ", n, "| type:", o.type, "| verts:", len(o.data.vertices),
                  "| dims:", tuple(round(x,4) for x in o.dimensions),
                  "| mats:", [m.name for m in o.data.materials])
            mm = o.data.materials[0]
            print("     nodes:", [nd.bl_idname for nd in mm.node_tree.nodes])
            for lk in mm.node_tree.links:
                print("     link:", lk.from_node.bl_idname+"."+lk.from_socket.name, "->", lk.to_node.bl_idname+"."+lk.to_socket.name)
            print("     surface_render_method:", mm.surface_render_method)
            ti = [nd for nd in mm.node_tree.nodes if nd.bl_idname=='ShaderNodeTexImage']
            if ti: print("     image:", ti[0].image.name, ti[0].image.size[:], "colorspace:", ti[0].image.colorspace_settings.name)
    except Exception as e:
        print("  EXC:", type(e).__name__, e); traceback.print_exc()

# A: filepath only (already known to fail, re-confirm)
attempt("A filepath only", filepath=LOGO, shader='EMISSION', use_transparency=True)

# B: directory + files collection
attempt("B directory + files",
        directory=d, files=[{"name": f}],
        shader='EMISSION', emit_strength=1.5, use_transparency=True,
        render_method='BLENDED', size_mode='ABSOLUTE', height=1.4,
        align_axis='+Y', location=(0,0,0.9))

# C: directory + files, PRINCIPLED shader
attempt("C PRINCIPLED shader",
        directory=d, files=[{"name": f}],
        shader='PRINCIPLED', use_transparency=True,
        render_method='BLENDED', size_mode='ABSOLUTE', height=2.0, align_axis='+Y')

# D: SHADELESS
attempt("D SHADELESS shader",
        directory=d, files=[{"name": f}],
        shader='SHADELESS', use_transparency=True,
        render_method='DITHERED', size_mode='ABSOLUTE', height=2.0, align_axis='+Y')

# E: filepath + files
attempt("E filepath + directory + files",
        filepath=LOGO, directory=d, files=[{"name": f}],
        shader='EMISSION', use_transparency=True, size_mode='ABSOLUTE', height=1.0)
