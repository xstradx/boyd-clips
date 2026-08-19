import sys, os, numpy as np
from PIL import Image, ImageDraw
def checker(w,h):
    a=np.zeros((h,w,4),np.uint8); a[:,:,3]=255
    yy,xx=np.mgrid[0:h,0:w]; c=(((xx//24)+(yy//24))%2).astype(bool)
    a[:,:,0]=np.where(c,112,80); a[:,:,1]=np.where(c,118,86); a[:,:,2]=np.where(c,130,96)
    return Image.fromarray(a)
def sheet(d, frames, box, cols, cw, out):
    x0,y0,x1,y1=box; ar=(y1-y0)/(x1-x0); ch=int(cw*ar)
    rows=(len(frames)+cols-1)//cols
    sh=Image.new('RGB',(cw*cols+4*(cols+1),(ch+20)*rows+4),(26,28,32))
    dr=ImageDraw.Draw(sh)
    bgfull=checker(1920,1080)
    for i,f in enumerate(frames):
        im=Image.open(os.path.join(d,'f_%04d.png'%f))
        bg=bgfull.copy(); bg.alpha_composite(im)
        c=bg.convert('RGB').crop(box).resize((cw,ch),Image.LANCZOS)
        x=(i%cols)*(cw+4)+4; y=(i//cols)*(ch+20)+4
        dr.text((x+2,y+2),'f%d'%f,fill=(190,196,208)); sh.paste(c,(x,y+18))
    sh.save(out); print('->',out)
