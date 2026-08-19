# BLENDER-CAPABILITY.md

**Driving Blender 5.0.1 headless from Python on this machine.**

```
C:\Program Files\Blender Foundation\Blender 5.0\blender.exe
Blender 5.0.1  (hash a3db93c5b259, built 2025-12-16 01:32:30)
Python 3.11.13 (MSC v.1929 64 bit AMD64)
Windows 11 Home 10.0.26200
```

Everything below was executed on this install. Where a claim rests on an earlier session's run
rather than a re-run, it is marked *(prior run)*. Where I re-verified it while writing this
document, the script is named. Scripts live in
`C:\Users\natha\Projects\boyd-clips\research\blender\scratch\`, renders in
`...\research\blender\renders\`.

**Read this before writing any bpy.** Blender 5.0 broke a large amount of what a language model
will recall from 3.x/4.x, and almost every break is silent or produces a `TypeError` that reads
like a typo rather than a version change. The version-specific traps section is the highest-value
part of this file.

**Docs note.** `docs.blender.org` returns hard HTTP 403 from this machine — WebFetch,
`Invoke-WebRequest` with a Chrome UA, and firecrawl (not installed) all fail, for
`/api/current/` and `/api/4.2/` alike. Every API claim here is therefore grounded in live
`bl_rna` introspection and executed tracebacks from this exact binary, which is the source the
online docs are generated from and is authoritative for this build specifically. Do not waste a
session re-trying the docs host.

---

## 0. The one-line sanity check

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe" -b --python-expr "import bpy; print(bpy.app.version_string)"
# -> 5.0.1
```

Standard invocation for real work:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe" -b --python "C:\path\to\script.py"
```

`-b` means no GUI, no window, no OpenGL context. A whole branded sting — empty scene to three
delivered files — ran end to end in a single `-b` process in 13.87 s wall clock *(prior run,
`scratch\15_end_to_end.py`)*.

---

## 1. Proven to work — with the exact idiom

Each idiom below is copy-pasteable and has been run.

### 1.1 Start from a genuinely empty scene

```python
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
sc.render.fps, sc.render.fps_base = 60, 1.0          # verified: effective 60.0
sc.frame_start, sc.frame_end = 1, 84
```

`objects after empty load: []`. Camera, light and world must all be created by you.
`scene.world` is `None` — assigning `bpy.data.worlds.new(...)` is required or you render
against nothing.

### 1.2 Render engines — probe by assignment, never by enum

```python
for eng in ("BLENDER_EEVEE", "CYCLES", "BLENDER_WORKBENCH"):
    sc.render.engine = eng      # all three succeed
```

Verified `arch_00_verify.py`:

```
enum_items: ['BLENDER_EEVEE']                       <- A LIE, see §4.1
assign OK -> BLENDER_EEVEE
assign OK -> CYCLES
assign OK -> BLENDER_WORKBENCH
assign FAIL BLENDER_EEVEE_NEXT :: enum "BLENDER_EEVEE_NEXT" not found in
    ('BLENDER_EEVEE', 'BLENDER_WORKBENCH', 'CYCLES')
```

There is no `BLENDER_EEVEE_NEXT`. EEVEE Next **is** `BLENDER_EEVEE` in 5.0.

Timings at 1920×1080, CPU *(prior run, `scratch\08_render.py`)*:

| engine | first frame | subsequent |
|---|---|---|
| `BLENDER_EEVEE` (taa 64) | 3.164 s | **0.342 s** |
| `CYCLES` (CPU, 32 spp + denoise) | 4.108 s | 3.614 s |
| `BLENDER_WORKBENCH` | 0.336 s | — |

The EEVEE first-frame figure is mostly one-time shader compilation. Quote 0.34 s as the
steady-state number, not 3.16 s. These are a 5-object scene with one area light — do not
extrapolate to production.

EEVEE in 5.0 is **bit-deterministic**: two renders of an identical configuration produced
0 differing pixels and an identical sha256 *(prior run, `scratch\crit_01_alpha.py`)*. That is
what makes A/B pixel-diff testing valid here.

### 1.3 Video output — the two-step gate and the ordering rule

```python
ims = sc.render.image_settings
ims.media_type  = 'VIDEO'        # NEW in 5.0 — gates file_format. MUST come first.
ims.file_format = 'FFMPEG'
ff = sc.render.ffmpeg
ff.format = 'QUICKTIME'
ff.codec  = 'QTRLE'              # codec BEFORE color_mode — the enum is computed from it
ims.color_mode = 'RGBA'          # only legal now
sc.render.filepath = r"...\out_"
bpy.ops.render.render(animation=True)
```

Verified `arch_00_verify.py`:

```
direct FFMPEG assign FAILED: enum "FFMPEG" not found in ('JPEG','OPEN_EXR','PNG',...)
after media_type='VIDEO':  VIDEO FFMPEG
RGBA under H264 REJECTED:  enum "RGBA" not found in ('BW','RGB')
RGBA under QTRLE:          RGBA
RGBA under PRORES default profile REJECTED  (profile was 422_PROXY)
RGBA under PRORES 4444:    RGBA
```

Set `ims.media_type = 'IMAGE'` to go back to still/sequence output.

### 1.4 Container/codec matrix — 14 of 15 combinations encode

*(prior run, `scratch\10_output.py`; all files on disk, all confirmed by external ffprobe)*

```
MPEG4+H264  MPEG4+H265  MPEG4+AV1  MPEG4+MPEG4
MKV+H264    MKV+FFV1    MKV+PRORES MKV+HUFFYUV
WEBM+WEBM   QUICKTIME+PRORES  QUICKTIME+QTRLE  QUICKTIME+H264
AVI+PNG     OGG+THEORA                            -- all OK
AVI+DNXHD                                          -- fails at defaults, see §2.6
```

Full enums this build exposes:

```
ffmpeg.format : MPEG4 MKV WEBM AVI DV FLASH MPEG1 MPEG2 OGG QUICKTIME
ffmpeg.codec  : NONE AV1 H264 H265 WEBM DNXHD DV FFV1 FLASH HUFFYUV MPEG1 MPEG2
                MPEG4 PNG PRORES QTRLE THEORA
audio_codec   : NONE AAC AC3 FLAC MP2 MP3 OPUS PCM VORBIS
file_format   : JPEG OPEN_EXR PNG WEBP BMP CINEON DPX IRIS JPEG2000 HDR TARGA
                TARGA_RAW TIFF OPEN_EXR_MULTILAYER FFMPEG
crf           : NONE LOSSLESS PERC_LOSSLESS HIGH MEDIUM LOW VERYLOW LOWEST
ffmpeg_preset : BEST GOOD REALTIME
prores_profile: 422_PROXY 422_LT 422_STD 422_HQ 4444 4444_XQ
```

### 1.5 Alpha that survives to disk

```python
sc.render.film_transparent = True
ims.color_mode = 'RGBA'
```

Alpha reaches the delivered file, confirmed by **external** ffprobe, in:

| container + codec | pix_fmt | alpha |
|---|---|---|
| QUICKTIME + QTRLE | `argb` | yes |
| QUICKTIME + PRORES, profile `4444` | `yuva444p12le` | yes |
| MKV + FFV1 | `bgra` | yes |
| AVI + PNG | `rgba` | yes |
| PNG sequence | `rgba` | yes |
| **WEBM + VP9** | `yuv420p` | **NO — silently discarded** |
| MPEG4 + H264 | `yuv420p` | no (expected) |

The alpha is **straight/unassociated**, proven at a 50 %-alpha pixel read externally:
PNG `(255,255,255,128)`, QTRLE `(255,255,255,128)`, ProRes 4444 `(255,255,255,129)` — RGB
holds full value while alpha drops *(prior run, `scratch\crit_04_video.py`)*.

EEVEE `BLENDED` + `film_transparent` writes **exact** alpha: at 1:1 texel mapping with
`filter_size=0`, mean and max alpha error against the source PNG were both `0.00000` across
both material topologies and both render methods *(prior run, `scratch\crit_01_alpha.py`)*.

### 1.6 Audio muxes in background mode — verified

This was listed as an open unknown by both earlier sessions. It works. `arch_05_audio.py`:

```python
se = sc.sequence_editor_create()
se.strips.new_sound(name="tone", filepath=WAV, channel=1, frame_start=1)
ims.media_type = 'VIDEO'; ims.file_format = 'FFMPEG'
ff.format = 'MPEG4'; ff.codec = 'H264'
ff.audio_codec = 'AAC'; ff.audio_bitrate = 192
bpy.ops.render.render(animation=True)
```

External ffprobe on the result:

```
stream,0,h264,video,640,360,60/1,1.000000,60
stream,1,aac,audio,48000,2,0/0,1.002000,48
```

`bpy.ops.sound.mixdown(filepath=..., container='WAV', codec='PCM', format='S16')` also works
headless (`{'FINISHED'}`, 195,662-byte WAV).

> **5.0 rename:** `SequenceEditor.sequences` and `.sequences_all` **do not exist**. They are
> `.strips` and `.strips_all`. `hasattr(se,'sequences') -> False`. Adders on `se.strips`:
> `new_clip new_effect new_image new_mask new_meta new_movie new_scene new_sound`.

### 1.7 Keyframing, and reading the curves back

Inserting is unchanged. **Reading moved.**

```python
obj.keyframe_insert('location', frame=1)          # unchanged, works
obj.keyframe_insert('location', frame=20, keytype='EXTREME')   # keytype arg works

ad = obj.animation_data
fcurves = ad.action.layers[0].strips[0].channelbag(ad.action_slot).fcurves
```

Verified `arch_00_verify.py`: `Action has .fcurves attr: False`;
`channelbag fcurves: [('scale',0,2), ('scale',1,2), ('scale',2,2)]`.

Enums this build accepts:

```
interpolation : CONSTANT LINEAR BEZIER SINE QUAD CUBIC QUART QUINT EXPO CIRC
                BACK BOUNCE ELASTIC
easing        : AUTO EASE_IN EASE_OUT EASE_IN_OUT
handle_*_type : FREE ALIGNED VECTOR AUTO AUTO_CLAMPED
keyframe type : KEYFRAME BREAKDOWN MOVING_HOLD EXTREME JITTER GENERATED
extrapolation : CONSTANT LINEAR
```

Default from `keyframe_insert` is `BEZIER` with `AUTO_CLAMPED` handles.

### 1.8 CSS-style cubic-bezier easing — the working idiom

Blender F-curve handles live in **(frame, value)** space, so a CSS `cubic-bezier(x1,y1,x2,y2)`
maps directly:

```python
def css_ease(fc, x1, y1, x2, y2):
    k0, k1 = fc.keyframe_points[0], fc.keyframe_points[1]
    k0.interpolation = 'BEZIER'
    for k in (k0, k1):
        k.handle_left_type = k.handle_right_type = 'FREE'
    f0, v0 = k0.co; f1, v1 = k1.co
    df, dv = f1 - f0, v1 - v0
    k0.handle_right = (f0 + x1 * df, v0 + y1 * dv)
    k1.handle_left  = (f0 + x2 * df, v0 + y2 * dv)
    fc.update()
```

Verified `arch_00_verify.py` with `cubic-bezier(0.42, 0, 0.58, 1)` over frames 1–6, values
0.2→1.0: handle types survived as `FREE/FREE`, evaluation
`[0.2, 0.2653, 0.4655, 0.7345, 0.9347, 1.0]` — symmetric, as it should be.
`FREE` handles genuinely persist; overshoot past the target is achievable purely from handle
placement (a prior run measured a peak of 1.1758 at t=0.58 on a 0→1 curve).

### 1.9 Shear — keyframable two ways, and it is exact

**FONT objects have a native shear property.** `TextCurve.shear`, described by this build as
*"Italic angle of the characters"*, range −1.0…1.0, and it is **tan(angle)**:

```python
tc = bpy.data.curves.new("T", type='FONT'); tc.font = bpy.data.fonts.load(TTF)
tc.shear = math.tan(math.radians(9.08))     # 0.159816
tc.keyframe_insert('shear', frame=1)
```

Verified `arch_01_shear.py` by measuring the evaluated mesh at four shear values; the measured
lean **delta** matched `atan(shear)` to within 0.15° at every value
(shear 0.10 → +5.70° measured vs 5.71° expected; 0.1598 → +9.12° vs 9.08°; 0.20 → +11.42° vs
11.31°). The absolute measurement carries a fixed glyph-shape offset — measure deltas, not
absolutes.

**Arbitrary meshes (including image planes) shear via a shape key**, which is keyframable and
carries the texture with it:

```python
plane.shape_key_add(name="Basis", from_mix=False)
sk = plane.shape_key_add(name="Shear", from_mix=False)
K = math.tan(math.radians(12.0))
for v in sk.data:
    v.co.x += v.co.y * K          # plane from import_as_mesh_planes lies in LOCAL XY
sk.value = 0.0; sk.keyframe_insert('value', frame=1)
sk.value = 1.0; sk.keyframe_insert('value', frame=10)
```

Verified `arch_02_shapekey.py` — fcurve at `key_blocks["Shear"].value`, evaluated lean
`0.000 / 3.154 / 8.951 / 11.997°` at frames 1/4/7/10, landing on the target 12.000°.
`arch_03_shearrender.py` renders it and the **texture shears with the quad** (a sheared
rectangle is a parallelogram, so the bilinear UV map stays affine and exact).

Note the local axis: `import_as_mesh_planes` builds the quad in local XY and rotates the
*object*, so shear x by **y**, not by z. My first attempt sheared by z and silently did nothing
(all four verts had z = 0).

### 1.10 Images as planes

```python
d, f = os.path.split(PNG)
r = bpy.ops.image.import_as_mesh_planes(
        directory=d, files=[{"name": f}],       # <-- both required
        shader='EMISSION', emit_strength=1.0,
        use_transparency=True, render_method='BLENDED',
        size_mode='ABSOLUTE', height=1.0, align_axis='-Y')
assert r == {'FINISHED'}
```

`align_axis` enum: `+X +Y +Z -X -Y -Z CAM CAM_AX`.
`shader` accepts `EMISSION` / `PRINCIPLED` / `SHADELESS`, each producing a different node graph.
Aspect ratio is preserved exactly (1413/540 = 2.6167 → dims 2.6167 × 1.0).

### 1.11 Manual image-texture plane (full control)

```python
img = bpy.data.images.load(PNG)               # 4 channels, STRAIGHT alpha, sRGB
mat = bpy.data.materials.new("M"); mat.use_nodes = True
nt = mat.node_tree; nt.nodes.clear()
tex   = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
emis  = nt.nodes.new('ShaderNodeEmission')
trans = nt.nodes.new('ShaderNodeBsdfTransparent')
mix   = nt.nodes.new('ShaderNodeMixShader')
out   = nt.nodes.new('ShaderNodeOutputMaterial')
nt.links.new(tex.outputs['Color'], emis.inputs['Color'])
nt.links.new(trans.outputs['BSDF'], mix.inputs[1])
nt.links.new(emis.outputs['Emission'], mix.inputs[2])
nt.links.new(tex.outputs['Alpha'], mix.inputs['Factor'])
nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])
mat.surface_render_method = 'BLENDED'
```

### 1.12 Compositor — the 5.0 shape

```python
ng = bpy.data.node_groups.new("MyComp", "CompositorNodeTree")
ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
rl = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc      # MANDATORY, see §2.3
go = ng.nodes.new("NodeGroupOutput")
ng.links.new(rl.outputs['Image'], go.inputs['Image'])
sc.compositing_node_group = ng
```

88 `CompositorNode*` types exist. Confirmed instantiating: `RLayers Viewer Image AlphaOver
Blur Glare Scale Translate Transform Rotate Invert SetAlpha Zcombine OutputFile MovieClip
CornerPin Displace PlaneTrackDeform EllipseMask BoxMask Lensdist ColorBalance Convolve
ImageCoordinates RelativeToPixel ImageInfo SceneTime Denoise Kuwahara Levels Exposure
Posterize Pixelate` plus `NodeGroupInput` / `NodeGroupOutput`. A subset of shader nodes also
work inside a compositor tree: `ShaderNodeMix ShaderNodeMath ShaderNodeValue ShaderNodeValToRGB
ShaderNodeMapRange ShaderNodeClamp ShaderNodeGamma ShaderNodeRGBCurve ShaderNodeVectorMath
ShaderNodeTexNoise ShaderNodeTexWhiteNoise ShaderNodeTexVoronoi`.

Animated compositor values evaluate per frame in `-b`, under both `render(animation=True)` and
manual `frame_set()` *(prior runs, `scratch\22_anim_comp.py`, `scratch\crit_03_framepaths.py`)*.
Compositor fcurve data paths look like
`nodes["Glare"].inputs[7].default_value`.

### 1.13 Per-frame film grain — proven, with the domain rule

```python
rl  = ng.nodes.new("CompositorNodeRLayers"); rl.scene = sc
ic  = ng.nodes.new("CompositorNodeImageCoordinates")
ng.links.new(rl.outputs['Image'], ic.inputs['Image'])   # <-- DOMAIN. see §4.6
st  = ng.nodes.new("CompositorNodeSceneTime")           # outputs: Seconds, Frame
wn  = ng.nodes.new("ShaderNodeTexWhiteNoise"); wn.noise_dimensions = '4D'
ng.links.new(ic.outputs['Pixel'], wn.inputs['Vector'])
ng.links.new(st.outputs['Frame'], wn.inputs['W'])       # reseeds every frame
mix = ng.nodes.new("ShaderNodeMix"); mix.data_type='RGBA'; mix.blend_type='ADD'
sel = lambda n, i: [s for s in n.inputs if s.identifier == i][0]
ng.links.new(rl.outputs['Image'],  sel(mix,'A_Color'))
ng.links.new(wn.outputs['Color'],  sel(mix,'B_Color'))
sel(mix,'Factor_Float').default_value = 0.0015          # LINEAR amplitude
res = [s for s in mix.outputs if s.identifier == 'Result_Color'][0]
ng.links.new(res, go.inputs['Image'])
```

Verified `arch_07_graintest.py` + external ffmpeg on a flat `#15181D` field, dither off:

```
grain_off : distinct=1     top=#15181D x57600      <- control, perfectly flat
grain_f1  : distinct=13377
grain_f2  : distinct=13384
f1 vs f2 differing bytes: 165168 of 172800          <- reseeds per frame
```

Amplitude is **linear**, so it is very non-linear in sRGB on a dark ground. Measured ladder on
`#15181D` (R channel, 21/255): `0.0005 → 22`, `0.0010 → 23`, `0.0015 → 24`, `0.0030 → 26`,
`0.0200 → 46`. My first test used 0.02 and lifted the whole ground to roughly `#2B2B2B` —
about 10× too strong. Start at 0.0015.

`CompositorNodeTexture` (the 4.x route to a noise texture) **does not exist** in 5.0.

### 1.14 Text objects

```python
fnt = bpy.data.fonts.load(r"...\Anton-Regular.ttf")
tc = bpy.data.curves.new("Txt", type='FONT')
tc.body = "TEXAS TRIAL TRACKER"
tc.font = fnt
tc.size = 1.0; tc.align_x = 'CENTER'; tc.align_y = 'CENTER'
tc.extrude = 0.0; tc.bevel_depth = 0.0           # keep flat for graphic work
tob = bpy.data.objects.new("Txt", tc)
sc.collection.objects.link(tob)
tob.rotation_euler = (math.radians(90), 0, 0)    # see §4.7
```

`fill_mode`: `FULL BACK FRONT HALF`. `align_x`: `LEFT CENTER RIGHT JUSTIFY FLUSH`.
Real geometry is generated (5,568 verts / 5,104 polys for a bevelled 4-character word).

### 1.15 Everything else that was proven *(prior runs)*

* Motion blur, both engines: `render.use_motion_blur`, `render.motion_blur_shutter` (0.5),
  `render.motion_blur_position` (`START/CENTER/END`), `render.motion_blur_shutter_curve`; EEVEE
  extras on `scene.eevee`: `motion_blur_steps`, `motion_blur_max`, `motion_blur_depth_scale`.
  Measured 4.28× (EEVEE) / 4.44× (Cycles) more lit pixels with blur on.
* DOF: `camera.data.dof.use_dof / focus_object / focus_distance / aperture_fstop /
  aperture_blades / aperture_rotation / aperture_ratio`. Works via both focus routes.
* Drivers: `fc = obj.driver_add('scale', 0)`; types `AVERAGE SUM SCRIPTED MIN MAX`. A
  `SCRIPTED` expression `'1 + z*0.5'` with `z = 4.0` evaluated to exactly 3.0.
* F-Modifiers: `NULL GENERATOR FNGENERATOR ENVELOPE CYCLES NOISE LIMITS STEPPED`. `NOISE`
  works for camera shake.
* Animation evaluates per frame in `-b` across all three render paths —
  `render(animation=True)`, `frame_set()` + `write_still`, and CLI `-s 1 -e 8 -a` — and all
  three produce **bit-identical** pixels including motion blur.
* `bpy.ops.preferences.addon_enable(module=...)` works in `-b`.

---

## 2. Broken, and the workaround

### 2.1 `bpy.ops.import_image.to_plane` — gone

`print(dir(bpy.ops.import_image)) -> []`. The `io_import_images_as_planes` addon is not
shipped. The full 5.0 addon list is `bl_pkg, cycles, hydra_storm, io_anim_bvh, io_curve_svg,
io_mesh_uv_layout, io_scene_fbx, io_scene_gltf2, node_wrangler, pose_library, rigify,
ui_translate, viewport_vr_preview`.

**Workaround:** built in as `bpy.ops.image.import_as_mesh_planes` (§1.10). No addon needed.
`bpy.ops.image.convert_to_mesh_plane` also exists.

### 2.2 `import_as_mesh_planes(filepath=...)` — silently cancels

```
Warning: Please select at least one image
  returned: {'CANCELLED'}      <- no exception raised
```

The most dangerous failure in this whole document: a script that does not check the return
value proceeds with a missing logo. **Workaround:** pass `directory=` + `files=[{"name": ...}]`
(§1.10) and `assert r == {'FINISHED'}` every time.

### 2.3 Compositor: `scene.node_tree` — gone; and the Group Input trap

`'node_tree' in bpy.types.Scene.bl_rna.properties -> False`. `Scene.use_nodes` survives but
emits `DeprecationWarning: expected to be removed in Blender 6.0`.

**Workaround:** §1.12.

**And the silent one:** wiring `NodeGroupInput → NodeGroupOutput` as a passthrough does *not*
receive the render. It renders **pure black** with no error — centre pixel `[0,0,0,0]`, whole-
frame mean R `0.00033` versus `0.6356` with the compositor off *(prior run)*. You must place a
`CompositorNodeRLayers` inside the group and drive the chain from `rl.outputs['Image']`.

### 2.4 `CompositorNodeComposite` / `MixRGB` / `Mix` / `Vignette` — undefined

Verified `arch_00_verify.py`: all four raise `RuntimeError: Node type ... undefined`.

**Workarounds:**
* Output → `NodeGroupOutput` wired from an interface output socket.
* Mixing → `ShaderNodeMix` with `data_type='RGBA'` and a `blend_type`; select sockets by
  `identifier` (`Factor_Float`, `A_Color`, `B_Color`, `Result_Color`), never by name.
* Vignette → `CompositorNodeEllipseMask` → `CompositorNodeBlur` → `ShaderNodeMix(MULTIPLY)`.
  Easy to overdo: a prior run crushed a whole frame to near-black at mask size 0.78/0.85 and
  factor 0.55.

### 2.5 `Action.fcurves` — gone

`AttributeError: 'Action' object has no attribute 'fcurves'`. Slotted/layered actions are
mandatory. **Workaround:** §1.7. `Action` also exposes `is_action_layered`,
`is_action_legacy`, `fcurve_ensure_for_datablock()`.

### 2.6 DNxHD fails at defaults

```
Error: ff_frame_thread_encoder_init failed
video.write | ERROR Couldn't initialize video codec: Invalid argument
```

Fails in AVI, MOV and MKV alike at 1920×1080/30. DNxHD only accepts a fixed table of
resolution/framerate/bitrate combinations and Blender's default CRF rate control emits none of
them. **Workaround:**

```python
ff.constant_rate_factor = 'NONE'
ff.video_bitrate = 185000; ff.minrate = 185000; ff.maxrate = 185000; ff.buffersize = 2000
```

Verified working at 30 fps and 25 fps; ffprobe reports `dnxhd,1920,1080,yuv422p`.

### 2.7 WEBM/VP9 silently discards alpha

No error. Blender accepts `color_mode='RGBA'`, renders, reports success — and ffprobe shows
`vp9,1920,1080,yuv420p`. **Workaround:** none inside Blender. Render QTRLE / ProRes 4444 /
FFV1 / a PNG sequence, and transcode externally with `ffmpeg -pix_fmt yuva420p` if VP9+alpha
is genuinely required.

### 2.8 `bpy.context.preferences.edit.keyframe_new_interpolation_type` is ignored

Setting it to `LINEAR` still produced `BEZIER` keys from `keyframe_insert()` in `-b`.
**Workaround:** set `kp.interpolation` explicitly on every keyframe after insertion and call
`fc.update()`. Same caution for `keyframe_new_handle_type`.

### 2.9 `SequenceEditor.sequences` — gone

`hasattr(se, 'sequences') -> False`, `sequences_all -> False`. **Workaround:** `.strips` /
`.strips_all` (§1.6).

### 2.10 `CompositorNodeTexture` — gone

**Workaround:** shader noise nodes inside the compositor tree (§1.13), or grain at delivery
with `ffmpeg -vf noise=...`.

### 2.11 Compositor node settings are no longer RNA properties

`glare.glare_type` → `KeyError`. The Glare node has **no** own RNA properties at all.
**Workaround:** they are input sockets — `glare.inputs['Type'].default_value = 'Bloom'`.
See §4.3 for the value-format trap.

### 2.12 Socket names are not unique

`ColorBalance` has `Lift` twice (VALUE `Base Lift`, RGBA `Color Lift`), likewise Gamma/Gain/
Offset/Power/Slope, and `Temperature`/`Tint` appear twice (input and output side).
`ShaderNodeMix` exposes 10 inputs with names `Factor ×2, A ×4, B ×4`. `Glare` now has
`Kernel` twice. `node.inputs['Name']` returns the **first** match and will hand you the wrong
socket type.

```python
sel = lambda n, i: [s for s in n.inputs if s.identifier == i][0]
```

**Always select by `.identifier`.**

---

## 3. What needs the GUI

Verified `scratch\gui_only.py` on this install:

| thing | result in `-b` |
|---|---|
| `import gpu` → any drawing call | `SystemError: GPU functions for drawing are not available in background mode` — `GPUOffScreen` cannot be created |
| `bpy.ops.render.opengl()` (viewport / workbench preview render) | `Error: Cannot use OpenGL render in background mode (no opengl context)` |
| `bpy.ops.wm.window_new()` | `poll() failed, context is incorrect` |
| `bpy.ops.screen.screenshot()` | `poll() failed, context is incorrect` |
| any `bpy.ops.view3d.*` | `poll() failed, context is incorrect` |
| `bpy.ops.sequencer.rendersize()` and most `sequencer` UI ops | `poll() failed, context is incorrect` |
| `bpy.context.area` / `bpy.context.region` | both `None` |

Screens exist as data (`Layout`, `Compositing`, `Animation`, … with 3–7 areas each) but they
have no window, so `temp_override` **cannot** rescue an area-polled operator — I tried, and
`view3d.snap_cursor_to_center` still fails poll.

**What this means in practice:** anything that needs a viewport is unavailable. Use
`BLENDER_WORKBENCH` (0.336 s/frame) as the substitute for a viewport preview — it is a real
render and needs no GL context. Everything in §1 works without a GUI, including full EEVEE.

**Still unproven:** EEVEE worked here on a machine with a display adapter. Whether EEVEE runs
on a headless CI box with no GPU at all is untested. Workbench and Cycles-CPU are the safe
fallbacks if that ever matters.

---

## 4. Version traps — where 5.0 differs from the 4.x you will recall

### 4.1 Half the enums lie, and the ones that lie are the dangerous ones

`bl_rna.properties[p].enum_items` is **not** a reliable capability probe. 5 of 10 properties
tested return a wrong (usually 1-element) set while assignment of other values succeeds
*(prior run, `scratch\crit_05_enums.py`; re-confirmed for engine and view_transform in
`arch_00_verify.py`)*:

| property | `enum_items` says | truth |
|---|---|---|
| `render.engine` | `['BLENDER_EEVEE']` | 3 values |
| `view_settings.view_transform` | `['NONE']` | **9 values** |
| `view_settings.look` | `['NONE']` | 10 values |
| `display_settings.display_device` | `['NONE']` | 6 values |
| `image_settings.file_format` | 15 values | 13 accepted at runtime |

The lying set is almost exactly the colour-management stack — the settings that silently
degrade output. Static enums (`colorspace name`, `media_type`, `ffmpeg.codec`, `cycles.device`)
are honest.

**The probe idiom** — assign junk and read the truth out of the exception:

```python
try:
    obj.prop = "__junk__"
except TypeError as e:
    print(str(e)[str(e).find("in ("):])
```

Live output from `arch_00_verify.py`:

```
view_transform true set:
  ('Standard', 'ACES 1.3', 'ACES 2.0', 'Khronos PBR Neutral', 'AgX',
   'Filmic', 'Filmic Log', 'False Color', 'Raw')
```

`ACES 2.0` and `Khronos PBR Neutral` are new and appear in no pre-5.0 training data. If you
write `'Filmic'` from memory you will get a legal but wrong-era transform.

Related: `bpy.types.CyclesRenderSettings` does not exist even though `scene.cycles` is a live
instance of it. Introspect the **instance**, not the type.

### 4.2 `bpy.data.images.load(p).pixels` is not a neutral pixel reader

This is the trap that silently invalidates hand-rolled image metrics, and both earlier sessions
built their verification on it. The reader is colour-managed and buffer-type-dependent:

| same flat `#15181D` field | Blender `Image.pixels` |
|---|---|
| written as 8-bit PNG (`is_float=False`) | `(0.0824, 0.0941, 0.1137)` — raw sRGB bytes |
| written as 16-bit PNG (`is_float=True`) | `(0.0075, 0.0091, 0.0123)` — linearised |

An 11× discrepancy for identical content; external ffmpeg reads `#15181D` from both.
`colorspace_settings.name = 'Non-Color'` makes the 16-bit read agree. Separately, a
*straight*-alpha file reads back **premultiplied** — a pixel stored as `(255,255,255,128)`
reports `(0.5, 0.5, 0.5)` at `A=0.5`, so alpha association cannot be determined this way at all.

**Rule: verify delivered pixels with external ffmpeg/ffprobe, not with `Image.pixels`.**

```powershell
& "C:\ffmpeg\ffmpeg.exe" -v error -y -i in.png -vf "crop=1:1:32:32" -f rawvideo -pix_fmt rgb24 px.raw
$b=[System.IO.File]::ReadAllBytes("px.raw"); "#{0:X2}{1:X2}{2:X2}" -f $b[0],$b[1],$b[2]
```

`Image.pixels` is fine for reading a *source* asset's alpha structure (§1.13 of the sting
spec uses it that way) — it is not fine for grading a *render*.

### 4.3 MENU sockets take display strings, and cannot be enumerated

```python
glare.inputs['Type'].default_value = 'FOG_GLOW'
# TypeError: enum "FOG_GLOW" not found in
#   ('Bloom','Ghosts','Streaks','Fog Glow','Simple Star','Sun Beams','Kernel')
glare.inputs['Type'].default_value = 'Fog Glow'      # correct
```

`socket.bl_rna.properties['default_value'].enum_items` is **empty**, and so are
`enum_items_static`, `enum_items_static_ui`, the `rna_type.properties` route, the
`bpy.types.NodeSocketMenu` type-level route, and every socket attribute matching
`menu|enum|item` — six routes checked, all dead. The junk-assignment trick (§4.1) is the only
discovery mechanism found.

**Do not skip setting these.** The Glare node's default `Type` is `'Streaks'`, not `'Bloom'` —
verified `arch_00_verify.py`. Adding a Glare node and not setting Type gives you streaks.
And the setting is not a no-op: all 15 pairwise render diffs across the six Glare types were
non-zero (0.084–0.811 mean |d|) *(prior run)*.

### 4.4 Bloom is compositor-only

`scene.eevee` has **zero** bloom-related properties (all 51 enumerated). Use
`CompositorNodeGlare` with `inputs['Type'] = 'Bloom'`.

### 4.5 Principled BSDF socket names are 4.x-era, not 3.x

Full 31-socket dump from this build:

```
 0 Base Color        1 Metallic          2 Roughness          3 IOR
 4 Alpha             5 Normal            6 Weight             7 Diffuse Roughness
 8 Subsurface Weight 9 Subsurface Radius 10 Subsurface Scale  11 Subsurface IOR
12 Subsurface Anisotropy                 13 Specular IOR Level
14 Specular Tint    15 Anisotropic      16 Anisotropic Rotation  17 Tangent
18 Transmission Weight  19 Coat Weight  20 Coat Roughness     21 Coat IOR
22 Coat Tint        23 Coat Normal      24 Sheen Weight       25 Sheen Roughness
26 Sheen Tint       27 Emission Color   28 Emission Strength
29 Thin Film Thickness                  30 Thin Film IOR
outputs: ['BSDF']
```

**Not** `'Emission'`, **not** `'Specular'`, **not** `'Subsurface'` / `'Transmission'` /
`'Clearcoat'` / `'Sheen'` as scalars.

### 4.6 Compositor nodes have a *domain*, and a node with no image input is a constant

New, and it fails silently. `CompositorNodeImageCoordinates` has an `Image` **input**; with it
unconnected the node has no domain and its output evaluates as a single flat value over the
whole frame. I lost a cycle to this: `ImageCoordinates → NodeGroupOutput` rendered
`distinct=1`, as did every noise chain fed from it. Wiring `RLayers.Image → ic.inputs['Image']`
fixed it immediately (`distinct=13377`). `CompositorNodeRelativeToPixel` and
`CompositorNodeImageInfo` have the same `Image` input for the same reason.

**Rule: if a compositor branch renders flat, check whether every node in it has a domain.**

### 4.7 FONT curves are born flat in XY facing +Z

A camera looking along +Y renders text edge-on until you set
`text_obj.rotation_euler = (math.radians(90), 0, 0)`. `import_as_mesh_planes` hides this
because `align_axis` orients the plane for you; text objects have no equivalent. Note that
`obj.dimensions` is local and does **not** change when you rotate — do not use it to verify.

### 4.8 `align_axis='+Y'` silently MIRRORS the graphic

New finding, and it is brutal for brand work. With the standard flat-graphic rig — camera at
`(0,-4,0)`, `rotation_euler=(radians(90),0,0)`, looking toward +Y — `align_axis='+Y'` produces
an object at `rot=(90°, 0°, 180°)` whose front faces *away* from the camera. Blender does not
backface-cull, so it renders the plane's back: **a horizontally mirrored logo, no warning.**

Verified `arch_04_mirror.py`. `renders/arch/mir_plusY.png` puts the TTT star on the **left**;
`renders/arch/mir_minusY.png` puts it on the **right**, which is correct.

**Rule: for a camera at −Y looking toward +Y, use `align_axis='-Y'`.** An earlier session's
end-to-end sting used `'+Y'`, so its logo was almost certainly mirrored.

### 4.9 `obj.dimensions` is stale after `obj.scale`

Reads the pre-scale value; no exception. **Workaround:** `bpy.context.view_layer.update()`
before reading, or `obj.evaluated_get(bpy.context.evaluated_depsgraph_get())` for evaluated
geometry.

### 4.10 `render.dither_intensity` defaults to 1.0

At 8-bit output a "flat" field is not bit-uniform — an 8-pixel row of a `#15181D` field reads
`15181D 15181D 15181D 15181D 15181D 14171C 15181D 15181D`. That is ±1 LSB and is *desirable*
(it is anti-banding), but it means "exact hex" claims need `dither_intensity = 0.0` to verify,
and 16-bit output makes it invisible at 8-bit precision. Ship with dither **on**; verify with
it off.

### 4.11 `use_nodes` is on the way out

`Material.use_nodes`, `World.use_nodes` and `Scene.use_nodes` all emit
`DeprecationWarning: expected to be removed in Blender 6.0`. They still work in 5.0. Any
pipeline built now should treat `node_tree` as always-present.

### 4.12 Hand-rolled image metrics lie more often than the API does

Two independent sessions produced a wrong conclusion from a plausible-looking metric:
a horizontal-gradient "sharpness" measure reported a *defocused* sphere as **sharper** with DOF
on (0.00108 → 0.00212), because defocusing a small bright emitter into a bokeh disc raises
gradient energy in the region. Blender images are also **bottom-up** — `y=0` is the bottom row —
which mis-places every hand-picked sample box.

**Rule: look at the render before trusting any metric you wrote yourself, and always run the
null-hypothesis control** (render the same thing twice, confirm 0 differing pixels) before
attributing a pixel difference to your change.

---

## 5. Colour management for brand-accurate output

**This is the section that matters most for branded work, and it is entirely 5.0-specific.**

### 5.1 The default ships the wrong colours

Scene default `view_transform` is `AgX`, `look` is `None`. Feeding correctly sRGB→linear
converted brand values through it and reading the delivered PNG with **external ffmpeg**
(`arch_01_shear.py` §E):

| brand | intent | **shipped at default AgX** |
|---|---|---|
| ground | `#15181D` | `#0E1116` |
| accent | `#D42B2B` | `#C4372A` |
| ink | `#F2EEE3` | `#C0BFBB` |

The ink lands as mid-grey. That is not a subtle miss.

### 5.2 The fix — output-side override, scene left alone

`ImageFormatSettings.color_management` is new in 5.0 (`FOLLOW_SCENE` / `OVERRIDE`) and lets the
*output* carry its own view transform while the scene keeps AgX for any lit 3D work:

```python
ims = sc.render.image_settings
ims.color_management = 'OVERRIDE'
ims.view_settings.view_transform = 'Standard'
ims.view_settings.look = 'None'
```

Verified `arch_00_verify.py` + external ffmpeg (`renders/arch/brand_*.png`):

```
bg  -> #15181D
red -> #D42B2B
ink -> #F2EEE3      <- exact, with sc.view_settings.view_transform still 'AgX'
```

The override **survives into FFMPEG video**, not just stills — previously confirmed exact in
PNG, QuickTime/QTRLE and ProRes 4444 *(prior run, `scratch\crit_04_video.py`)*.

### 5.3 Feed linear, always

Colours set on nodes are **linear**. Convert once:

```python
def srgb_to_linear(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
```

Brand constants, computed on this machine:

| hex | linear RGB |
|---|---|
| `#15181D` ground | `(0.007499, 0.009134, 0.012286)` |
| `#F2EEE3` ink | `(0.887923, 0.854993, 0.768151)` |
| `#D42B2B` accent | `(0.658375, 0.024158, 0.024158)` |
| `#D02D2E` (the *wrong* red in the current logo asset) | `(0.630757, 0.026241, 0.027321)` |

### 5.4 Checklist for any brand deliverable

1. `ims.color_management = 'OVERRIDE'`; `ims.view_settings.view_transform = 'Standard'`;
   `ims.view_settings.look = 'None'`.
2. All colours fed as linear via `srgb_to_linear`.
3. Flat graphic elements use `ShaderNodeEmission` (or `import_as_mesh_planes(shader='EMISSION')`)
   so no light transport touches the value.
4. `render.dither_intensity = 1.0` for delivery, `0.0` for verification renders.
5. Verify the delivered file with external ffmpeg, never with `Image.pixels` (§4.2).
6. For alpha work: `film_transparent = True`, material `surface_render_method = 'BLENDED'`,
   `color_mode = 'RGBA'` — set **after** the codec (§1.3).

---

## 6. Still unknown

Honest gaps. Do not assume these work.

* **GPU.** Every Cycles timing here is `device='CPU'`. `scene.cycles.device` accepts `'GPU'`
  but `compute_device_type` (CUDA/OPTIX/HIP/ONEAPI) was never enumerated and no GPU render was
  ever run.
* **Headless-without-display.** EEVEE worked here; whether it works on a box with no display
  adapter is untested.
* **Motion blur beyond translation.** Rotation blur and deformation blur (armature / shape key /
  geometry nodes) were never tested. Shape-key shear + motion blur in particular is untested and
  is directly relevant to the sting.
* **OPEN_EXR / render passes.** Never exercised, despite being the natural compositing format.
* **Cycles at production sample counts**, denoiser choice (OIDN vs OptiX), rolling shutter,
  per-object motion steps.
* **Geometry nodes, modifiers, linking/appending, SVG import** (`io_curve_svg` is present but
  untested — it is the obvious route for the redrawn vector mark).
* **`CompositorNodeAlphaOver`'s new `Straight Alpha` and `Type` inputs** — proven to alter
  output, not proven to behave like the 4.x node.
* **The 4.x→5.0 migration list is not exhaustive.** It covers what these sessions touched.
  Docs are 403, so assume any untouched API may also have moved.

---

## 7. Files

```
research\blender\
├─ BLENDER-CAPABILITY.md        this file
├─ STING-SPEC.md                the Texas Trial Tracker sting build spec
├─ scratch\
│   arch_00_verify.py           re-verification of every load-bearing idiom here
│   arch_01_shear.py            TextCurve.shear; AgX control renders
│   arch_02_shapekey.py         shape-key shear, correct axis
│   arch_03_shearrender.py      sheared texture render + source alpha audit
│   arch_04_mirror.py           align_axis mirror proof
│   arch_05_audio.py            headless audio mux + sound.mixdown
│   arch_06_grain.py            node availability inventory
│   arch_07_graintest.py        working per-frame grain
│   arch_08_graindiag.py        domain isolation
│   gui_only.py                 what is unavailable in -b
│   crit_01..07_*.py            critic's audit (alpha, colour, frame paths, video, enums,
│                               dither/DOF, image readback)
│   boyd_anim.py                slotted-action helpers (get_fcurves / find_fcurve /
│                               cubic_bezier_ease)
│   01..22_*.py                 original recon sweep
└─ renders\arch\                this session's verification renders
```
