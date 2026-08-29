import numpy as np, cv2
from skimage import color as skcolor
import finish as F, composite as C, surfmeas as M, edgeprof as E, grainchar as G

plate=cv2.imread('D_4437.png'); judge=cv2.imread('J_3944.png')
a=cv2.imread('_judge_alpha.png',cv2.IMREAD_GRAYSCALE)
def chain(post_blend,sharp):
    def f(t,s):
        x=F.s1_chroma_clean(t,2); x=F.s2_deblock(x,3); x=F.s3_deconv(x,0.8,12)
        x=cv2.resize(x,s,interpolation=cv2.INTER_LANCZOS4)
        x=F.s3b_deconv_clamped(x,1.3,16,1,post_blend)
        return F.s7_output_sharpen(x,0.7,sharp,2.0)
    return f
def falloff(canvas,m,dL,dC=0.10,radius=90):
    d=cv2.distanceTransform((m<=127).astype(np.uint8),cv2.DIST_L2,5)
    w=np.clip(1.0-d/radius,0,1)**1.5; w[m>127]=0
    lab=skcolor.rgb2lab(cv2.cvtColor(canvas,cv2.COLOR_BGR2RGB).astype(np.float64)/255.0)
    lab[:,:,0]=np.clip(lab[:,:,0]+dL*w,0,100); lab[:,:,1]*=(1-dC*w); lab[:,:,2]*=(1-dC*w)
    return cv2.cvtColor(np.clip(skcolor.lab2rgb(lab)*255,0,255).astype(np.uint8),cv2.COLOR_RGB2BGR)
def full(img,tag,m):
    Y=M.luma(img); d={}; d.update(M.bandpass_rms(Y)); d.update(M.radial_spectrum(Y)); d.update(M.acutance(Y))
    e=E.analyse(Y); s=C.sep(img,m); cv2.imwrite('_t.png',img); g=G.run('_t.png') or {}
    print('%-14s s1=%5.2f s2=%5.2f hi/mid=%.4f cut=%.3f slope=%6.1f grad=%5.2f nF=%5.2f nG=%5.2f | rise=%4.2f over=%4.1f under=%4.1f | gsig=%4.2f fwhm=%4.2f chr=%4.2f | hfratio=%4.2f dE00=%4.1f'%(
      tag,d['band_s1'],d['band_s2'],d['spec_hi_over_mid'],d['spec_cutoff_cpp'],d['spec_slope'],d['grad_mean'],
      M.flat_noise(Y) or 0,M.noise_immerkaer(Y),e.get('rise_10_90_px',0),e.get('overshoot_pct',0),e.get('undershoot_pct',0),
      g.get('sigma',0),g.get('acf_fwhm_px',0),g.get('chroma_frac',0),s['hf_ratio'],s['dE00_edge']),flush=True)

cur,m=C.build(plate,judge,C.fin_current,C.fin_current,a); full(cur,'CURRENT',m)
c,m=C.build(plate,judge,chain(0.75,0.40),chain(0.85,0.55),a)
c=F.s6_grain(c,sigma=5.2,size=0.48)
c=falloff(c,m,+10.0)
cv2.imwrite('FINAL_candidate.png',c); cv2.imwrite('FINAL_candidate_q95.jpg',c,[cv2.IMWRITE_JPEG_QUALITY,95])
full(c,'CANDIDATE',m)
full(cv2.imread('FINAL_candidate_q95.jpg'),'CAND q95',m)
