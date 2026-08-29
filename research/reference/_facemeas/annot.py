import cv2,json,numpy as np,os
OUT="C:/Users/natha/Projects/boyd-clips/research/reference/_facemeas"
rows=json.load(open(OUT+"/faces.json"))
ROOT="C:/Users/natha/Projects/boyd-clips/research/reference"
def pathof(r):
    return (ROOT+"/competitor/thumbs/"+r["file"]) if r["grp"]=="ATC" else (ROOT+"/courtroomtime/thumbs/"+r["file"])
def sheet(sub,name,cols=4):
    TW,TH=440,247
    rowsN=(len(sub)+cols-1)//cols
    canv=np.full((rowsN*(TH+22),cols*TW,3),30,np.uint8)
    for i,r in enumerate(sub):
        im=cv2.imread(pathof(r)); im=cv2.resize(im,(TW,TH))
        sx,sy=TW/r["W"],TH/r["H"]
        for f in r["faces"]:
            x,y,w,h=int(f["x"]*sx),int(f["y"]*sy),int(f["w"]*sx),int(f["h"]*sy)
            c=(0,255,0) if f["conf"]>0.85 else ((0,200,255) if f["conf"]>0.7 else (0,0,255))
            cv2.rectangle(im,(x,y),(x+w,y+h),c,2)
            cv2.putText(im,f"{f['conf']:.2f}",(x,max(10,y-3)),0,0.38,c,1,cv2.LINE_AA)
            lm=f["lm"]
            for k in range(5):
                cv2.circle(im,(int(lm[2*k]*sx),int(lm[2*k+1]*sy)),2,(255,0,255),-1)
        rr,cc=divmod(i,cols)
        canv[rr*(TH+22)+22:(rr+1)*(TH+22),cc*TW:(cc+1)*TW]=im
        cv2.putText(canv,f"{r['file'][:40]} v={r['views']} n={len(r['faces'])}",
                    (cc*TW+4,rr*(TH+22)+15),0,0.42,(255,255,255),1,cv2.LINE_AA)
    cv2.imwrite(OUT+"/"+name,canv,[cv2.IMWRITE_JPEG_QUALITY,88]); print(name,canv.shape)
sheet([r for r in rows if r["grp"]=="ATC"],"annot_atc.jpg")
sheet([r for r in rows if r["grp"]=="CT_top"],"annot_top.jpg")
sheet([r for r in rows if r["grp"]=="CT_bot"],"annot_bot.jpg")
