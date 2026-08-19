import numpy as np, parselmouth, soundfile as sf
from parselmouth.praat import call

def edit(src, dst, fn, floor=60, ceil=170):
    s = parselmouth.Sound(src)
    man = call(s, "To Manipulation", 0.01, floor, ceil)
    pt  = call(man, "Extract pitch tier")
    n   = call(pt, "Get number of points")
    ts  = np.array([call(pt,"Get time from index",i+1) for i in range(n)])
    fs  = np.array([call(pt,"Get value at index",i+1) for i in range(n)])
    new = fn(ts, fs)
    npt = call("Create PitchTier","p", s.xmin, s.xmax)
    for t,f in zip(ts,new): call(npt,"Add point",float(t),float(np.clip(f,floor+1,ceil-1)))
    call([man,npt],"Replace pitch tier")
    out = call(man,"Get resynthesis (overlap-add)")
    out.save(dst, parselmouth.SoundFileFormat.WAV)
    return ts, fs, new

def stats(p):
    s=parselmouth.Sound(p); pi=s.to_pitch_ac(time_step=0.01,pitch_floor=60,pitch_ceiling=170)
    f=pi.selected_array['frequency']; f=f[f>0]
    return round(float(np.median(f)),1), round(float(np.std(12*np.log2(f/np.median(f)))),2), round(s.duration,3)

src="prosody/d100.wav"
# 1) NULL round trip - measure PSOLA damage
edit(src,"prosody/null.wav", lambda t,f: f)
# 2) EXCURSION EXPANSION: stretch deviations from median by 1.45x
def expand(t,f):
    m=np.median(f); return m*np.power(2.0,1.45*np.log2(f/m))
edit(src,"prosody/expand.wav", expand)
# 3) FINAL FALL: last 0.45s of file falls an extra 3.0 st, ramped
def fall(t,f):
    m=np.median(f); end=t.max(); w=np.clip((t-(end-0.45))/0.45,0,1)
    return f*np.power(2.0,(-3.0*w)/12.0)
edit(src,"prosody/fall.wav", fall)
# 4) both
def both(t,f):
    return fall(t,expand(t,f))
edit(src,"prosody/expand_fall.wav", both)
for n in ["d100","null","expand","fall","expand_fall"]:
    print(f"{n:12s} f0_med={stats('prosody/'+n+'.wav')[0]:6.1f}  f0_sd_st={stats('prosody/'+n+'.wav')[1]:5.2f}  dur={stats('prosody/'+n+'.wav')[2]}")
