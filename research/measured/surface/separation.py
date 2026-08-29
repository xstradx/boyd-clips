"""Subject / ground colour separation.

Mattes the main subject with BiRefNet (MIT), then measures how the finished image
separates that subject from what is behind it:
  dL_edge   : mean L* inside a 20px band inside the contour minus a 20px band outside
  dE00_edge : CIEDE2000 between those two bands
  dL_glob / dC_glob : whole-subject vs whole-background
  rim_gain  : L* of the 4px ring just inside the contour minus L* of the subject body
              (detects a deliberate rim light / edge lift)
  bg_blur   : ratio of high-frequency energy in background vs subject
"""
import sys, os, glob, json
import numpy as np, cv2
from skimage import color as skcolor
from rembg import remove, new_session

SESSION = None


def matte(path, model='birefnet-general-lite'):
    global SESSION
    if SESSION is None:
        SESSION = new_session(model)
    data = open(path, 'rb').read()
    out = remove(data, session=SESSION, only_mask=True)
    arr = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_UNCHANGED)
    if arr is None:
        return None
    if arr.ndim == 3:
        arr = arr[:, :, -1]
    return arr


def hi_energy(Y):
    return float(np.sqrt(((Y - cv2.GaussianBlur(Y, (0, 0), 2)) ** 2).mean()))


def run(path, cache_dir):
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    H, W = bgr.shape[:2]
    mp = os.path.join(cache_dir, os.path.basename(path) + '.mask.png')
    if os.path.exists(mp):
        m = cv2.imread(mp, cv2.IMREAD_GRAYSCALE)
    else:
        m = matte(path)
        if m is None:
            return None
        cv2.imwrite(mp, m)
    if m.shape[:2] != (H, W):
        m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
    fg = m > 200
    bgm = m < 40
    if fg.sum() < 0.02 * H * W or bgm.sum() < 0.02 * H * W:
        return {'file': os.path.basename(path), 'skip': 'no subject'}
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    lab = skcolor.rgb2lab(rgb)
    L, a, b = lab[:, :, 0], lab[:, :, 1], lab[:, :, 2]
    C = np.hypot(a, b)

    hard = (m > 127).astype(np.uint8)
    din = cv2.distanceTransform(hard, cv2.DIST_L2, 5)
    dout = cv2.distanceTransform(1 - hard, cv2.DIST_L2, 5)
    band_in = (din > 2) & (din <= 22)
    band_out = (dout > 2) & (dout <= 22)
    ring = (din > 0) & (din <= 4)
    body = din > 12

    def mlab(msk):
        return np.array([L[msk].mean(), a[msk].mean(), b[msk].mean()])

    out = {'file': os.path.basename(path), 'fg_frac': float(fg.mean())}
    if band_in.sum() > 500 and band_out.sum() > 500:
        li, lo = mlab(band_in), mlab(band_out)
        out['dL_edge'] = float(li[0] - lo[0])
        out['absdL_edge'] = float(abs(li[0] - lo[0]))
        out['dE00_edge'] = float(skcolor.deltaE_ciede2000(li.reshape(1, 1, 3), lo.reshape(1, 1, 3))[0, 0])
        out['dC_edge'] = float(np.hypot(li[1], li[2]) - np.hypot(lo[1], lo[2]))
    lf, lb = mlab(fg), mlab(bgm)
    out['dL_glob'] = float(lf[0] - lb[0])
    out['absdL_glob'] = float(abs(lf[0] - lb[0]))
    out['dE00_glob'] = float(skcolor.deltaE_ciede2000(lf.reshape(1, 1, 3), lb.reshape(1, 1, 3))[0, 0])
    out['C_fg'] = float(C[fg].mean())
    out['C_bg'] = float(C[bgm].mean())
    if ring.sum() > 200 and body.sum() > 500:
        out['rim_gain'] = float(L[ring].mean() - L[body].mean())
    Y = 0.2126 * bgr[:, :, 2] + 0.7152 * bgr[:, :, 1] + 0.0722 * bgr[:, :, 0]
    hp = np.abs(Y - cv2.GaussianBlur(Y, (0, 0), 2))
    out['hf_fg'] = float(hp[fg].mean())
    out['hf_bg'] = float(hp[bgm].mean())
    out['hf_ratio_fg_over_bg'] = float(hp[fg].mean() / max(hp[bgm].mean(), 1e-6))
    return out


if __name__ == '__main__':
    cache = sys.argv[1]
    os.makedirs(cache, exist_ok=True)
    rows = []
    for pat in sys.argv[2:]:
        for f in sorted(glob.glob(pat)):
            try:
                r = run(f, cache)
            except Exception as e:
                r = {'file': os.path.basename(f), 'err': str(e)}
            if r:
                rows.append(r)
                print(json.dumps(r), flush=True)
    json.dump(rows, open(os.path.join(cache, 'separation.json'), 'w'), indent=1)
