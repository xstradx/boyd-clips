# arch_05_audio.py -- can Blender 5.0.1 mux AUDIO into an mp4 in BACKGROUND mode?
# This is the one deliverable-blocking unknown both prior agents left open.
import bpy, os

OUT = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders\arch"
WAV = r"C:\Users\natha\Projects\boyd-clips\research\blender\scratch\arch_tone.wav"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = 640; sc.render.resolution_y = 360
sc.render.fps = 60; sc.render.fps_base = 1.0
sc.frame_start = 1; sc.frame_end = 60
print("fps:", sc.render.fps, "/", sc.render.fps_base, "-> effective", sc.render.fps / sc.render.fps_base)

cd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("C", cd)
sc.collection.objects.link(cam); sc.camera = cam
bpy.ops.mesh.primitive_cube_add()

print("scene.sequence_editor before:", sc.sequence_editor)
se = sc.sequence_editor_create()
print("sequence_editor_create ->", se)
print("strips collection attrs:", [a for a in dir(se) if 'strip' in a.lower() or 'sequence' in a.lower()])
snd = None
for adder in ("new_sound", "new_sound"):
    try:
        snd = se.strips.new_sound(name="tone", filepath=WAV, channel=1, frame_start=1)
        print("se.strips.new_sound OK ->", snd, snd.type)
        break
    except AttributeError as e:
        print("se.strips.new_sound FAILED:", e)
        try:
            snd = se.sequences.new_sound(name="tone", filepath=WAV, channel=1, frame_start=1)
            print("se.sequences.new_sound OK ->", snd, snd.type)
        except Exception as e2:
            print("se.sequences.new_sound FAILED:", e2)
        break

ims = sc.render.image_settings
ims.media_type = 'VIDEO'
ims.file_format = 'FFMPEG'
ff = sc.render.ffmpeg
ff.format = 'MPEG4'
ff.codec = 'H264'
ff.audio_codec = 'AAC'
ff.audio_bitrate = 192
ims.color_mode = 'RGB'
sc.render.filepath = os.path.join(OUT, "audio_test_")
bpy.ops.render.render(animation=True)
print("rendered ->", sc.render.filepath)

print("\n--- bpy.ops.sound.mixdown available? ---")
print("sound ops:", [o for o in dir(bpy.ops.sound)])
try:
    r = bpy.ops.sound.mixdown(filepath=os.path.join(OUT, "mixdown.wav"),
                              container='WAV', codec='PCM', format='S16')
    print("mixdown ->", r)
except Exception as e:
    print("mixdown FAILED:", type(e).__name__, e)
