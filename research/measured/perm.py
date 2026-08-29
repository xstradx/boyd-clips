import json, itertools, numpy as np
from scipy.stats import fisher_exact, mannwhitneyu
d=json.load(open(r'C:/Users/natha/Projects/boyd-clips/research/reference/_facemeas/final.json'))
s=d['surv']
top=[x['eyed_px_at210'] for x in s if x['grp']=='CT_top']
bot=[x['eyed_px_at210'] for x in s if x['grp']=='CT_bot']
atc=[(x['file'],x['views'],x['eyed_px_at210']) for x in s if x['grp']=='ATC']
print("CT_top n=%d min=%.3f med=%.3f"%(len(top),min(top),np.median(top)))
print("CT_bot n=%d min=%.3f med=%.3f"%(len(bot),min(bot),np.median(bot)))
print("MWU one-sided p=%.4f"%mannwhitneyu(top,bot,alternative='greater').pvalue)
print("MWU two-sided p=%.4f"%mannwhitneyu(top,bot,alternative='two-sided').pvalue)

allv=np.array(top+bot); lab=np.array([1]*len(top)+[0]*len(bot))
def minp(v,l):
    best=1.0; bt=None
    for t in sorted(set(v)):
        a=int(((v>=t)&(l==1)).sum()); b=int(((v<t)&(l==1)).sum())
        c=int(((v>=t)&(l==0)).sum()); e=int(((v<t)&(l==0)).sum())
        p=fisher_exact([[a,b],[c,e]])[1]
        if p<best: best,bt=p,t
    return best,bt
obs,bt=minp(allv,lab)
print("best-threshold Fisher p=%.5f at t=%.3f (this is the p they reported)"%(obs,bt))
rng=np.random.default_rng(0); cnt=0; N=20000
for _ in range(N):
    pl=rng.permutation(lab)
    if minp(allv,pl)[0]<=obs+1e-12: cnt+=1
print("PERMUTATION-CORRECTED p for best-threshold search: %.4f  (%d/%d)"%(cnt/N,cnt,N))
print()
print("ATC (all winners, 42k-1.2M views) eye sep at 210px:")
for f,v,e in sorted(atc,key=lambda x:-x[1]): print("  %8d  %6.2f px  %s"%(v,e,f))
below=[x for x in atc if x[2]<13.0]
print("ATC below the claimed 13.0px floor: %d/%d"%(len(below),len(atc)))
print("ATC median=%.2f  CT_top median=%.2f"%(np.median([x[2] for x in atc]),np.median(top)))
