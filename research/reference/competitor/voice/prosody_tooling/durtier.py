import numpy as np, parselmouth, json
from parselmouth.praat import call
SW=json.load(open("prosody/d100_words.json"))
s=parselmouth.Sound("prosody/d100.wav")
man=call(s,"To Manipulation",0.01,60,170)
dt=call("Create DurationTier","d",s.xmin,s.xmax)
call(dt,"Add point",s.xmin,1.0); call(dt,"Add point",s.xmax,1.0)
# stress BEXAR (word idx 11) : lengthen 1.35x, and add a +2.5st accent peak on it
w=[x for x in SW if 'Bexar' in x['w']][0]
a,b=w['s'],w['e']; print("Bexar",a,b)
for t,v in [(a-0.02,1.0),(a+0.005,1.35),(b-0.005,1.35),(b+0.02,1.0)]:
    call(dt,"Add point",float(t),float(v))
call([man,dt],"Replace duration tier")
pt=call(man,"Extract pitch tier"); n=call(pt,"Get number of points")
ts=np.array([call(pt,"Get time from index",i+1) for i in range(n)])
fs=np.array([call(pt,"Get value at index",i+1) for i in range(n)])
c=(a+b)/2; wdt=(b-a)/2
acc=2.5*np.exp(-0.5*((ts-c)/max(wdt,1e-3))**2)
npt=call("Create PitchTier","p",s.xmin,s.xmax)
for t,f,g in zip(ts,fs,acc): call(npt,"Add point",float(t),float(np.clip(f*2**(g/12),61,169)))
call([man,npt],"Replace pitch tier")
call(man,"Get resynthesis (overlap-add)").save("prosody/accent_bexar.wav",parselmouth.SoundFileFormat.WAV)
o=parselmouth.Sound("prosody/accent_bexar.wav")
print("dur %.3f -> %.3f  (+%.0f ms)"%(s.duration,o.duration,1000*(o.duration-s.duration)))
for p,l in [("prosody/d100.wav","base"),("prosody/accent_bexar.wav","accented")]:
    x=parselmouth.Sound(p); pi=x.to_pitch_ac(time_step=0.01,pitch_floor=60,pitch_ceiling=170)
    f=pi.selected_array['frequency']; fv=f[f>0]
    print(l,"f0_med %.1f  peak_in_Bexar %.1f"%(np.median(fv), np.nanmax([pi.get_value_at_time(t) or np.nan for t in np.arange(a,b,0.01)])))
