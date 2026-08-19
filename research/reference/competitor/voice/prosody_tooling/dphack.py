import numpy as np, soundfile as sf, supertonic
tts = supertonic.TTS(model="supertonic-3"); vs = tts.get_voice_style("M3")
TEXT = "On March 25th, 2023, Erik Michael Moody was booked into the Bexar County jail."
m = tts.model
orig = m.dp_ort.run
captured = {}
def spy(out, feed):
    r = orig(out, feed)
    captured['dur'] = r[0]; captured['ids'] = feed['text_ids']
    return r
m.dp_ort.run = spy
wav,_ = tts.synthesize(TEXT, vs, speed=1.0)
d = captured['dur']; ids = captured['ids']
print("dur shape", d.shape, "dtype", d.dtype, "sum", float(np.sum(d)))
print("ids shape", ids.shape)
print("first 25 dur", np.round(np.asarray(d).ravel()[:25],4))
np.save("prosody/dur.npy", d)
