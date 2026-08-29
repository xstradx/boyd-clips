import cv2, numpy as np, os, json
def runs(row, lo=3, hi=22):
    out=[]; i=0; n=len(row)
    while i<n:
        if row[i]:
            j=i
            while j<n and row[j]: j+=1
            if lo<=j-i<=hi: out.append(((i+j)/2.0, j-i))
            i=j
        else: i+=1
    return out
def detect(path, thr=228, need=5):
    img=cv2.resize(cv2.imread(path),(1280,720))
    m=(img.min(axis=2)>thr)
    ys=[int(720*f) for f in (0.15,0.28,0.41,0.54,0.67,0.80)]
    R=[runs(m[y]) for y in ys]
    found=[]
    for a in range(len(ys)):
        for c0,w0 in R[a]:
            for b in range(len(ys)-1,a,-1):
                for cb,wb in R[b]:
                    slope=(cb-c0)/(ys[b]-ys[a])
                    if abs(slope)>0.45: continue
                    hits=0; widths=[]
                    for k in range(len(ys)):
                        pred=c0+slope*(ys[k]-ys[a])
                        h=[(c,w) for c,w in R[k] if abs(c-pred)<=8]
                        if h: hits+=1; widths.append(h[0][1])
                    if hits>=need:
                        xm=c0+slope*(360-ys[a])
                        if any(abs(xm-f['x_mid'])<50 for f in found): continue
                        found.append(dict(x_mid=float(xm),deg=float(np.degrees(np.arctan(slope))),
                                          w=float(np.median(widths)),hits=hits))
    return found
res={}
for f in sorted(os.listdir('ccthumbs')):
    if f.endswith('.jpg'): res[f[:-4]]=detect('ccthumbs/'+f)
json.dump(res,open('gutters2.json','w'))
for k in ['oK0djKDK48k','IkdQu8XQoLQ','xUk_32XNrbs','cHmdsh8Mw_Q','huloi4jUQpE']:
    print(k,res.get(k))
