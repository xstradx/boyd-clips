import os, glob, sys
import numpy as np, cv2
from rembg import new_session, remove
from PIL import Image
OUT='C:/Users/natha/Projects/boyd-clips/research/reference/_geom/mattes'
os.makedirs(OUT,exist_ok=True)
sess=new_session('birefnet-general-lite')   # MIT licence
fs=sorted(glob.glob('C:/Users/natha/Projects/boyd-clips/research/reference/competitor/thumbs/*.jpg'))+ \
   sorted(glob.glob('C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime/thumbs/*.jpg'))
for i,f in enumerate(fs):
    o=os.path.join(OUT, os.path.basename(f)[:-4]+'.png')
    if os.path.exists(o): print('skip',i,os.path.basename(f)); continue
    im=Image.open(f).convert('RGB')
    r=remove(im, session=sess, only_mask=True)
    r.save(o)
    print('ok',i,os.path.basename(f), flush=True)
print('DONE')
