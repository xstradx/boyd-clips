import numpy as np, soundfile as sf, supertonic, os, json
tts = supertonic.TTS(model="supertonic-3")
vs = tts.get_voice_style("M3")
TEXT = "On March 25th, 2023, Erik Michael Moody was booked into the Bexar County jail."
core = tts.pipeline.model if hasattr(tts,'pipeline') else None
print("pipeline attrs:", [a for a in dir(tts) if not a.startswith('_')])
wav, dur = tts.synthesize(TEXT, vs, speed=1.0)
sf.write("prosody/base.wav", np.asarray(wav).squeeze(), tts.sample_rate)
print("base dur", dur)
