import numpy as np, soundfile as sf, pyworld as pw, parselmouth, time
x,fs = sf.read("prosody/d100.wav"); x=np.asarray(x,dtype=np.float64)
t0=time.time()
f0,t = pw.harvest(x,fs,f0_floor=60.0,f0_ceil=170.0,frame_period=5.0)
f0 = pw.stonemask(x,f0,t,fs)
sp = pw.cheaptrick(x,f0,t,fs); ap = pw.d4c(x,f0,t,fs)
y_null = pw.synthesize(f0,sp,ap,fs,5.0)
sf.write("prosody/world_null.wav", y_null, fs)
v=f0>0; m=np.median(f0[v])
f0e=f0.copy(); f0e[v]=m*np.power(2.0,1.45*np.log2(f0[v]/m))
sf.write("prosody/world_expand.wav", pw.synthesize(f0e,sp,ap,fs,5.0), fs)
print("world elapsed %.2fs  frames=%d  voiced=%.1f%%"%(time.time()-t0,len(f0),100*v.mean()))
def st(p):
    s=parselmouth.Sound(p); pi=s.to_pitch_ac(time_step=0.01,pitch_floor=60,pitch_ceiling=170)
    f=pi.selected_array['frequency']; f=f[f>0]
    return round(float(np.median(f)),1), round(float(np.std(12*np.log2(f/np.median(f)))),2)
for n in ["d100","world_null","world_expand","null","expand"]:
    print(n, st("prosody/"+n+".wav"))
# spectral distortion of null round trips vs source
import scipy.signal as ss
def mcd(a,b):
    A,_=sf.read(a); B,_=sf.read(b); n=min(len(A),len(B)); A=A[:n];B=B[:n]
    fa=np.abs(ss.stft(A,nperseg=512)[2]); fb=np.abs(ss.stft(B,nperseg=512)[2])
    return round(float(np.mean(np.abs(20*np.log10(fa+1e-8)-20*np.log10(fb+1e-8)))),2)
print("mean |dB| spectral diff  praat_null:", mcd("prosody/d100.wav","prosody/null.wav"),
      " world_null:", mcd("prosody/d100.wav","prosody/world_null.wav"))
