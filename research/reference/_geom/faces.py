import cv2, numpy as np, glob, os, json, sys
MODEL='C:/Users/natha/Projects/boyd-clips/models/yunet2023.onnx'

def detect(img, conf=0.55):
    H,W=img.shape[:2]
    out=[]
    # multi-scale: run at several upscales so small faces are found
    for sc in (1.0,1.5,2.0,3.0):
        w,h=int(W*sc),int(H*sc)
        im=cv2.resize(img,(w,h),interpolation=cv2.INTER_CUBIC) if sc!=1.0 else img
        d=cv2.FaceDetectorYN.create(MODEL,'',(w,h),conf,0.3,5000)
        _,f=d.detect(im)
        if f is None: continue
        for r in f:
            x,y,bw,bh=r[:4]/sc
            out.append([float(x),float(y),float(bw),float(bh),float(r[-1])]+[float(v)/sc for v in r[4:14]])
    if not out: return []
    out.sort(key=lambda r:-r[4])
    keep=[]
    for r in out:
        ok=True
        for k in keep:
            # IoU
            ax1,ay1,ax2,ay2=r[0],r[1],r[0]+r[2],r[1]+r[3]
            bx1,by1,bx2,by2=k[0],k[1],k[0]+k[2],k[1]+k[3]
            ix=max(0,min(ax2,bx2)-max(ax1,bx1)); iy=max(0,min(ay2,by2)-max(ay1,by1))
            inter=ix*iy
            smaller=min(r[2]*r[3],k[2]*k[3])
            if inter/(smaller+1e-9) > 0.45: ok=False;break
        if ok: keep.append(r)
    return keep

if __name__=='__main__':
    fs=sorted(glob.glob('C:/Users/natha/Projects/boyd-clips/research/reference/competitor/thumbs/*.jpg'))+ \
       sorted(glob.glob('C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime/thumbs/*.jpg'))
    res={}
    os.makedirs('C:/Users/natha/Projects/boyd-clips/research/reference/_geom/ov_face',exist_ok=True)
    for f in fs:
        im=cv2.imread(f); H,W=im.shape[:2]
        ks=detect(im)
        res[os.path.basename(f)]=[{'x':k[0],'y':k[1],'w':k[2],'h':k[3],'conf':k[4],
            'lm':[[k[5+2*i],k[6+2*i]] for i in range(5)]} for k in ks]
        ov=im.copy()
        for k in ks:
            cv2.rectangle(ov,(int(k[0]),int(k[1])),(int(k[0]+k[2]),int(k[1]+k[3])),(0,255,0),3)
            cv2.putText(ov,f"{k[4]:.2f} h={k[3]:.0f}",(int(k[0]),int(k[1])-6),0,0.7,(0,255,0),2)
            for i in range(5):
                cv2.circle(ov,(int(k[5+2*i]),int(k[6+2*i])),3,(0,0,255),-1)
        cv2.imwrite('C:/Users/natha/Projects/boyd-clips/research/reference/_geom/ov_face/'+os.path.basename(f)[:-4]+'.png',ov)
        print(os.path.basename(f), len(ks), [f"{k[2]:.0f}x{k[3]:.0f}@{k[0]:.0f},{k[1]:.0f}" for k in ks])
    json.dump(res,open('C:/Users/natha/Projects/boyd-clips/research/reference/_geom/faces.json','w'),indent=1)
