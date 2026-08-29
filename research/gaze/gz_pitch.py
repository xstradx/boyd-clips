import cv2, numpy as np, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gz_measure import detect_faces, face_metrics
MP4 = "C:/Users/natha/Projects/boyd-clips/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4"
W,H,X,Y = 612,338,18,190
def grab(t):
    p = subprocess.run(["ffmpeg","-v","error","-ss","%.2f"%t,"-i",MP4,"-frames:v","1",
                        "-f","image2pipe","-vcodec","png","-"],capture_output=True)
    return cv2.imdecode(np.frombuffer(p.stdout,np.uint8),cv2.IMREAD_COLOR) if p.stdout else None
rows=[]
for i in range(50):
    t = 1143.0*(i+0.5)/50
    fr = grab(t)
    if fr is None: continue
    tile = fr[Y:Y+H, X:X+W]
    s = 640.0/tile.shape[1]
    big = cv2.resize(tile,None,fx=s,fy=s,interpolation=cv2.INTER_CUBIC)
    fs = detect_faces(big, score=0.6)
    if not fs: continue
    m = face_metrics(sorted(fs,key=lambda r:-r[3])[0], big.shape[0], big.shape[1])
    if abs(m["nose_dev"])>0.8: continue
    rows.append((m["nose_v"], t, big, m))
rows.sort(key=lambda r:r[0])
sel = rows[:4] + rows[-4:]
tiles=[]
for nv,t,big,m in sel:
    im = cv2.resize(big,(400,int(400*big.shape[0]/big.shape[1])))
    for lx,ly in m["lm"]:
        cv2.circle(im,(int(lx*400/big.shape[1]),int(ly*400/big.shape[1])),3,(0,0,255),-1)
    lab="nose_v=%+.3f t=%.0fs"%(nv,t)
    cv2.putText(im,lab,(6,24),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,0,0),4)
    cv2.putText(im,lab,(6,24),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,255),1)
    tiles.append(im)
ch=max(t.shape[0] for t in tiles)
rws=[]
for i in range(0,8,4):
    ck=[cv2.copyMakeBorder(t,0,ch-t.shape[0],0,0,cv2.BORDER_CONSTANT,value=(20,20,20)) for t in tiles[i:i+4]]
    rws.append(np.hstack(ck))
cv2.imwrite("C:/Users/natha/Projects/boyd-clips/research/gaze/SHEET_pitch.png",np.vstack(rws))
print("TOP ROW = 4 LOWEST nose_v ; BOTTOM ROW = 4 HIGHEST nose_v")
print("low:", ["%.3f"%r[0] for r in rows[:4]], " high:", ["%.3f"%r[0] for r in rows[-4:]])
