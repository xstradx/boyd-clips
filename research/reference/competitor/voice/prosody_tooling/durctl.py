import numpy as np, soundfile as sf, supertonic, parselmouth
tts = supertonic.TTS(model="supertonic-3"); vs = tts.get_voice_style("M3")
TEXT = "On March 25th, 2023, Erik Michael Moody was booked into the Bexar County jail."
m = tts.model; orig = m.dp_ort.run
def mk(scale):
    def f(out, feed):
        r = list(orig(out, feed)); r[0] = (r[0]*scale).astype(np.float32); return r
    return f
for sc,name in [(1.0,"d100"),(0.88,"d088"),(1.15,"d115")]:
    m.dp_ort.run = mk(sc)
    w,_ = tts.synthesize(TEXT, vs, speed=1.0)
    w = np.asarray(w).squeeze()
    p = f"prosody/{name}.wav"; sf.write(p, w, tts.sample_rate)
    s = parselmouth.Sound(p); pi = s.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=170)
    f0 = pi.selected_array['frequency']; f0 = f0[f0>0]
    print(f"{name} scale={sc} dur={s.duration:.3f}s f0_med={np.median(f0):.1f}Hz f0_sd_st={np.std(12*np.log2(f0/np.median(f0))):.2f}")
