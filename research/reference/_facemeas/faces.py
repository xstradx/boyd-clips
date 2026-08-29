import cv2, numpy as np, json, os, glob, math

ROOT="C:/Users/natha/Projects/boyd-clips/research/reference"
OUT="C:/Users/natha/Projects/boyd-clips/research/reference/_facemeas"
MODEL="C:/Users/natha/Projects/boyd-clips/models/yunet2023.onnx"

def files():
    out=[]
    for f in sorted(glob.glob(ROOT+"/competitor/thumbs/*.jpg")):
        b=os.path.basename(f); out.append(("ATC", b, f, int(b.split("_")[0])))
    for f in sorted(glob.glob(ROOT+"/courtroomtime/thumbs/*.jpg")):
        b=os.path.basename(f); out.append(("CT_"+b[:3], b, f, int(b.split("_")[1])))
    return out

def iou(a,b):
    ax,ay,aw,ah=a[:4]; bx,by,bw,bh=b[:4]
    x1=max(ax,bx); y1=max(ay,by); x2=min(ax+aw,bx+bw); y2=min(ay+ah,by+bh)
    if x2<=x1 or y2<=y1: return 0.0
    inter=(x2-x1)*(y2-y1)
    return inter/float(aw*ah+bw*bh-inter)

def detect_multiscale(img, conf=0.55):
    """Run YuNet at several input scales; merge by IoU keeping highest conf."""
    H,W=img.shape[:2]
    allf=[]
    for s in (0.5,1.0,1.6,2.4):
        w=int(W*s); h=int(H*s)
        if w<64 or w>4200: continue
        im=cv2.resize(img,(w,h),interpolation=cv2.INTER_CUBIC if s>1 else cv2.INTER_AREA)
        det=cv2.FaceDetectorYN.create(MODEL,"",(w,h),conf,0.3,5000)
        det.setInputSize((w,h))
        n,fs=det.detect(im)
        if fs is None: continue
        for f in fs:
            f=f.astype(float).copy()
            f[:14]/=s          # bbox(4) + 5 landmarks(10) = 14 coords
            allf.append((f,s))
    allf.sort(key=lambda t:-t[0][14])
    kept=[]
    for f,s in allf:
        if all(iou(f,k[0])<0.35 for k in kept): kept.append((f,s))
    return kept

def pose(f):
    """5 landmarks: r-eye, l-eye, nose, r-mouth, l-mouth (image coords)."""
    re=np.array(f[4:6]); le=np.array(f[6:8]); no=np.array(f[8:10])
    rm=np.array(f[10:12]); lm=np.array(f[12:14])
    eyed=np.linalg.norm(le-re)
    if eyed<1e-6: return None
    emid=(le+re)/2.0; mmid=(lm+rm)/2.0
    # roll from eye line
    roll=math.degrees(math.atan2(le[1]-re[1], le[0]-re[0]))
    # yaw proxy: nose x offset from eye midpoint, in eye-distance units,
    # projected onto the eye-line direction so roll doesn't contaminate it
    ev=(le-re)/eyed
    yaw=float(np.dot(no-emid, ev))/eyed
    # pitch proxy: nose sits between eye line and mouth line; 0.5 = neutral
    perp=np.array([-ev[1],ev[0]])
    d_eye=float(np.dot(no-emid,perp)); d_mouth=float(np.dot(mmid-emid,perp))
    pitch = d_eye/d_mouth if abs(d_mouth)>1e-6 else float('nan')
    mouthw=float(np.linalg.norm(lm-rm))
    return dict(eyed=eyed, roll=roll, yaw=yaw, pitch=pitch,
                mouthw_over_eyed=mouthw/eyed,
                facelen_over_eyed=float(np.linalg.norm(mmid-emid))/eyed)

rows=[]
for grp,b,path,views in files():
    img=cv2.imread(path)
    H,W=img.shape[:2]
    kept=detect_multiscale(img)
    faces=[]
    for f,s in kept:
        x,y,w,h=f[:4]
        p=pose(f)
        faces.append(dict(x=float(x),y=float(y),w=float(w),h=float(h),conf=float(f[14]),
                          scale=s, lm=[float(v) for v in f[4:14]], pose=p))
    rows.append(dict(grp=grp,file=b,views=views,W=W,H=H,faces=faces))
    print(f"{b:52s} {W}x{H} faces={len(faces)}")

json.dump(rows,open(OUT+"/faces.json","w"),indent=1)
print("wrote",OUT+"/faces.json")
