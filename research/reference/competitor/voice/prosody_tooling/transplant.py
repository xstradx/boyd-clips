import numpy as np, parselmouth, json
from parselmouth.praat import call
HUM=r"C:\Users\natha\Projects\boyd-clips\research\reference\competitor\voice\ek3_open.wav"
HW =json.load(open(r"C:\Users\natha\Projects\boyd-clips\research\reference\competitor\voice\ek3_words.json"))
SW =json.load(open("prosody/d100_words.json"))
N=14; hw=HW[:N]; sw=SW[:N]
# human pitch contour over its own window ONLY (avoid the whole-file contamination bug)
h=parselmouth.Sound(HUM).extract_part(from_time=hw[0]['s']-0.05, to_time=hw[-1]['e']+0.05, preserve_times=True)
hp=h.to_pitch_ac(time_step=0.01,pitch_floor=60,pitch_ceiling=170)
hf=hp.selected_array['frequency']; ht=hp.xs()
hv=hf>0; hmed=float(np.median(hf[hv]))
print("human window %.2f-%.2fs  f0_med=%.1f  sd_st=%.2f  n_voiced=%d"%(
  hw[0]['s'],hw[-1]['e'],hmed,float(np.std(12*np.log2(hf[hv]/hmed))),hv.sum()))
# piecewise-linear time map synthetic -> human, anchored on word starts+ends
sx=[]; hx=[]
for a,b in zip(sw,hw):
    sx += [a['s'], a['e']]; hx += [b['s'], b['e']]
sx=np.array(sx); hx=np.array(hx)
k=np.argsort(sx); sx=sx[k]; hx=hx[k]
u,i=np.unique(sx,return_index=True); sx=u; hx=hx[i]
u,i=np.unique(hx,return_index=True); hx=u; sx=sx[i]
# synthetic manipulation
s=parselmouth.Sound("prosody/d100.wav")
sp=s.to_pitch_ac(time_step=0.01,pitch_floor=60,pitch_ceiling=170)
sfv=sp.selected_array['frequency']; smed=float(np.median(sfv[sfv>0]))
man=call(s,"To Manipulation",0.01,60,170)
pt=call(man,"Extract pitch tier"); n=call(pt,"Get number of points")
ts=np.array([call(pt,"Get time from index",i+1) for i in range(n)])
fs=np.array([call(pt,"Get value at index",i+1) for i in range(n)])
# map each synthetic pitch point to human time, read human f0, rescale to synth median
htm=np.interp(ts,sx,hx)
hfv=np.where(hv,hf,np.nan)
def hread(t):
    j=np.argmin(np.abs(ht-t))
    for d in range(0,12):
        for jj in (j-d,j+d):
            if 0<=jj<len(hfv) and hv[jj]: return hfv[jj]
    return np.nan
hvals=np.array([hread(t) for t in htm])
newf=np.where(np.isnan(hvals), fs, smed*(hvals/hmed))
# blend 100% and 60% strength
for strength,name in [(1.0,"tp100"),(0.6,"tp060")]:
    blend=fs*np.power(newf/fs,strength)
    npt=call("Create PitchTier","p",s.xmin,s.xmax)
    for t,f in zip(ts,blend): call(npt,"Add point",float(t),float(np.clip(f,61,169)))
    m2=call(s,"To Manipulation",0.01,60,170)
    call([m2,npt],"Replace pitch tier")
    call(m2,"Get resynthesis (overlap-add)").save("prosody/%s.wav"%name, parselmouth.SoundFileFormat.WAV)
def st(p):
    x=parselmouth.Sound(p); pi=x.to_pitch_ac(time_step=0.01,pitch_floor=60,pitch_ceiling=170)
    f=pi.selected_array['frequency']; f=f[f>0]
    return round(float(np.median(f)),1), round(float(np.std(12*np.log2(f/np.median(f)))),2)
for nme in ["d100","tp060","tp100"]: print(nme, st("prosody/"+nme+".wav"))
