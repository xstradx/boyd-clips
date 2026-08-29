import cv2, numpy as np, os, sys, json

def collect(path, H=1500):
    img = cv2.imread(path); h0,w0=img.shape[:2]; s=H/h0
    img = cv2.resize(img,(int(w0*s),H)); h,w=img.shape[:2]
    g = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    cands=[]
    o = cv2.threshold(g,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    bins=[o,255-o,
          cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY,151,-25),
          cv2.adaptiveThreshold(g,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,151,-25)]
    for b in bins:
        n,lab,st,cen = cv2.connectedComponentsWithStats(b,8)
        for i in range(1,n):
            x,y,cw,ch,a = st[i]
            if ch < 0.020*h or ch > 0.22*h: continue
            if cw < 0.18*ch or cw > 1.5*ch: continue
            fill=a/(cw*ch)
            if fill<0.18 or fill>0.92: continue
            if x<=1 or y<=1 or x+cw>=w-1 or y+ch>=h-1: continue
            if y < 0.13*h: continue
            m = (lab[y:y+ch,x:x+cw]==i)
            vals = g[y:y+ch,x:x+cw][m]
            if vals.std() > 22: continue          # glyph ink is flat; faces are not
            cands.append((int(x),int(y),int(cw),int(ch)))
    cands.sort(key=lambda r:-r[2]*r[3]); keep=[]
    for r in cands:
        ok=True
        for k in keep:
            ix=max(0,min(r[0]+r[2],k[0]+k[2])-max(r[0],k[0])); iy=max(0,min(r[1]+r[3],k[1]+k[3])-max(r[1],k[1]))
            if ix*iy>0.5*min(r[2]*r[3],k[2]*k[3]): ok=False;break
        if ok: keep.append(r)
    return keep,w,h,img

def analyse(path,draw=None,minn=5):
    keep,w,h,img=collect(path)
    hs=sorted({r[3] for r in keep},reverse=True); cap=None;grp=[]
    for c in hs:
        gg=[r for r in keep if 0.78*c<=r[3]<=1.28*c]
        if len(gg)>=minn: cap=c; grp=gg; break
    if cap is None: return None
    cap=float(np.median([r[3] for r in grp]))
    grp.sort(key=lambda r:r[1]+r[3]/2)
    lines=[]
    for g in grp:
        yc=g[1]+g[3]/2; placed=False
        for L in lines:
            if abs(yc-L['yc'])<0.55*cap: L['g'].append(g); L['yc']=float(np.mean([q[1]+q[3]/2 for q in L['g']])); placed=True;break
        if not placed: lines.append({'yc':yc,'g':[g]})
    lines=[L for L in lines if len(L['g'])>=2]
    if not lines: return None
    grp=[g for L in lines for g in L['g']]
    cap=float(np.median([r[3] for r in grp]))
    words=0; percl=[]
    for L in lines:
        gs=sorted(L['g'],key=lambda r:r[0]); wcount=1
        for a,b in zip(gs,gs[1:]):
            if b[0]-(a[0]+a[2])>0.45*cap: wcount+=1
        words+=wcount; percl.append(len(gs))
    xs=[g[0] for g in grp]; xe=[g[0]+g[2] for g in grp]; ys=[g[1] for g in grp]; ye=[g[1]+g[3] for g in grp]
    if draw:
        for x,y,cw,ch in grp: cv2.rectangle(img,(x,y),(x+cw,y+ch),(0,0,255),3)
        cv2.imwrite(draw,img)
    return dict(cap_pct=100*cap/h, n_lines=len(lines), words=words, chars=len(grp),
                max_chars_line=max(percl), top=float(min(ys))/h, bot=float(max(ye))/h,
                left=float(min(xs))/w, right=float(max(xe))/w, cy=float(np.mean(ys+ye))/h)

if __name__=='__main__':
    d,outj=sys.argv[1],sys.argv[2]; res={}
    for f in sorted(os.listdir(d)):
        try: a=analyse(os.path.join(d,f))
        except Exception as e: a=None
        if a: res[f]=a
    json.dump(res,open(outj,'w')); print('ok',len(res),'/',len(os.listdir(d)))
