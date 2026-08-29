import sys, os, json, numpy as np
sys.path.insert(0,r'C:/Users/natha/Projects/boyd-clips/research/outsider')
from glyph3 import analyse
CT=r'C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime/thumbs'
ATC=r'C:/Users/natha/Projects/boyd-clips/research/reference/competitor/thumbs'
def run(d):
    out={}
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(('.jpg','.jpeg','.png')): continue
        try: a=analyse(os.path.join(d,f))
        except Exception as e: a=None
        out[f]=a
    return out
ct=run(CT); atc=run(ATC)
def rep(name,res,filt=None):
    v=[(f,a) for f,a in res.items() if a and (filt is None or filt(f))]
    caps=[a['cap_pct'] for _,a in v]
    if not caps: print(name,"no detections"); return
    print("%-10s n=%2d/%2d  cap%%H med=%.2f  p25=%.2f p75=%.2f  min=%.2f max=%.2f  words med=%.1f  lines med=%.1f  left med=%.3f right med=%.3f"%(
        name,len(v),sum(1 for f in res if (filt is None or filt(f))),np.median(caps),np.percentile(caps,25),np.percentile(caps,75),min(caps),max(caps),
        np.median([a['words'] for _,a in v]),np.median([a['n_lines'] for _,a in v]),
        np.median([a['left'] for _,a in v]),np.median([a['right'] for _,a in v])))
rep('CT_top',ct,lambda f:f.startswith('top_'))
rep('CT_bot',ct,lambda f:f.startswith('bot_'))
rep('ATC',atc)
print()
print("Outsider territory reference figures: NY Post splash cap = 15.2%H (p25 14.0 p75 16.5); 2024 one-sheet title cap = 7.47%H (p25 4.90 p75 9.53)")
print("Outsider tabloid block spans left 4.3% -> right 92.8% of width; poster 22.6% -> 79.7%")
json.dump({'ct':ct,'atc':atc},open('capmeas.json','w'))
