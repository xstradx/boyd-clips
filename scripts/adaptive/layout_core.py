"""Parametric thumbnail layout: measure the frame, derive the arrangement.

No hand-tuned coordinates. Everything below is computed from the decoded frame.

Sources for the mechanism (all fetched, see the report):
  * SmartText (MIT, github.com/intchous/SmartText, generate_candidates.py):
    coarse-grid saliency -> forbid the top 1/sali_coef cells -> sweep font size
    -> get_top_k_submatrix() picks the MIN-SUM fixed-size window. We do the
    same thing with integral images instead of torch avg_pool2d.
  * PosterLayout CVPR2023 (github.com/PKU-ICST-MIPL/PosterLayout-CVPR2023,
    eval.py): the objective. metrics_occ (mean saliency under an element,
    lower better), metrics_uti (fraction of non-salient area used, higher
    better), metrics_rea (mean Sobel gradient under text, lower better),
    metrics_ove (pairwise IoU, lower better), metrics_ali (min over the six
    alignment channels of -log10(1-delta), lower better).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

# ---------------------------------------------------------------- integral --

def integral(a: np.ndarray) -> np.ndarray:
    return cv2.integral(a.astype(np.float64))


def rect_sum(ii: np.ndarray, x0, y0, x1, y1) -> np.ndarray:
    """Sum over [x0,x1) x [y0,y1) from a summed-area table. Vectorised."""
    return (ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0])


# ------------------------------------------------------------- perception --

@dataclass
class Face:
    x: float; y: float; w: float; h: float
    lex: float; ley: float; rex: float; rey: float
    nx: float; ny: float
    mlx: float; mly: float; mrx: float; mry: float
    score: float

    @property
    def cx(self): return self.x + self.w / 2

    @property
    def cy(self): return self.y + self.h / 2

    @property
    def interocular(self): return math.hypot(self.rex - self.lex, self.rey - self.ley)

    @property
    def yaw(self):
        """Signed head turn. >0 = facing image-right, <0 = facing image-left.

        nose offset from the eye midpoint, normalised by interocular distance.
        0 = straight down the lens. This is what decides which frame edge the
        cut-out bleeds off: a head must look INTO the composition, not out.
        """
        io = self.interocular
        if io < 1e-6:
            return 0.0
        return ((self.nx - (self.lex + self.rex) / 2) / io)

    @property
    def roll(self):
        return math.degrees(math.atan2(self.rey - self.ley, self.rex - self.lex))

    @property
    def pitch_proxy(self):
        """Eye-midpoint -> nose vertical run over interocular. Rises when the
        head tilts DOWN (Nathan rejects every down-looking Boyd frame)."""
        io = self.interocular
        if io < 1e-6:
            return 0.0
        return (self.ny - (self.ley + self.rey) / 2) / io


def detect_faces(bgr, model_path, thresh=0.55) -> list[Face]:
    h, w = bgr.shape[:2]
    det = cv2.FaceDetectorYN.create(model_path, "", (w, h), thresh, 0.3, 5000)
    det.setInputSize((w, h))
    _, raw = det.detect(bgr)
    out = []
    if raw is None:
        return out
    for r in raw:
        out.append(Face(*[float(v) for v in r[:14]], score=float(r[14])))
    return sorted(out, key=lambda f: -f.h)


def person_matte(bgr, session) -> np.ndarray:
    """BiRefNet alpha in [0,1]. birefnet-* weights are MIT; rembg's DEFAULT
    (bria-rmbg) is CC BY-NC and must never be used on a monetised channel."""
    from rembg import remove
    from PIL import Image
    rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    cut = remove(rgb, session=session, post_process_mask=True)
    return np.asarray(cut.split()[-1], dtype=np.float32) / 255.0


_OCR = None


def burnin_mask(bgr, use_ocr=True) -> np.ndarray:
    """Zoom's burned-in furniture inside a tile: the active-speaker ring and
    the court's own caption slab ("187TH DC" / "Judge Boyd").

    The caption is found by OCR and masked at its returned polygon, not by
    assuming a corner - it sits bottom-left of the LEFT tile in CARTHIEF and
    bottom-left of the RIGHT tile in OFFERUP, and a colour threshold for
    "white text" also selects this courtroom's white ceiling and walls
    (measured: a (S<40)&(V>200) rule marks 16.6% of the OFFERUP tile and
    rejects every candidate crop).
    """
    global _OCR
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    Hh, S, V = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    b, g, r = [bgr[..., i].astype(int) for i in range(3)]
    # Zoom's active-speaker ring: near-pure green, far from both other channels
    green = ((g - np.maximum(r, b)) > 55) & (g > 165)
    m = green.astype(np.uint8)
    if use_ocr:
        try:
            if _OCR is None:
                from rapidocr_onnxruntime import RapidOCR
                _OCR = RapidOCR()
            res, _ = _OCR(bgr)
            for box, txt, conf in (res or []):
                p = np.array(box, dtype=np.int32)
                x0, y0 = p[:, 0].min(), p[:, 1].min()
                x1, y1 = p[:, 0].max(), p[:, 1].max()
                pad = int(0.35 * (y1 - y0))
                cv2.rectangle(m, (max(0, x0 - pad), max(0, y0 - pad)),
                              (min(w, x1 + pad), min(h, y1 + pad)), 1, -1)
        except Exception:
            pass
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 9), np.uint8))
    return m.astype(np.float32)


def letterbox_bounds(bgr, tol=10):
    """Active picture area. Zoom renders black bars whose height changes with
    the tile layout (CARTHIEF/OFFERUP have them, SANCHEZ's 3-up does not)."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    rows = g.max(axis=1) > tol
    cols = g.max(axis=0) > tol
    ys = np.flatnonzero(rows); xs = np.flatnonzero(cols)
    if len(ys) == 0 or len(xs) == 0:
        return 0, 0, bgr.shape[1], bgr.shape[0]
    return int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1


def grad_map(bgr) -> np.ndarray:
    """PosterLayout metrics_rea, verbatim: sqrt((Sobel_x^2+Sobel_y^2)/2),
    normalised by its own max. Low = smooth = readable under type."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(g, -1, 1, 0)
    gy = cv2.Sobel(g, -1, 0, 1)
    gxy = np.sqrt((gx.astype(np.float32) ** 2 + gy.astype(np.float32) ** 2) / 2)
    m = gxy.max()
    return gxy / m if m > 0 else gxy


# ------------------------------------------------------------------ fields --

@dataclass
class Field:
    """Everything the placer is allowed to know about one candidate plate."""
    bgr: np.ndarray
    sal: np.ndarray        # [0,1] subject occupancy (matte U face boxes)
    grad: np.ndarray       # [0,1] Sobel energy
    forbid: np.ndarray     # {0,1} hard no-go (person + burn-in, dilated)
    people: np.ndarray = None   # true person pixels only: matte U burn-in,
                                # undilated. The arrow is tested against THIS,
                                # because the shipped measurement was 'red
                                # pixels sitting on a person', not on a box.
    faces: list = field(default_factory=list)
    ii_sal: np.ndarray = None
    ii_grad: np.ndarray = None
    ii_forbid: np.ndarray = None
    ii_notsal: np.ndarray = None

    def bake(self):
        self.ii_sal = integral(self.sal)
        self.ii_grad = integral(self.grad)
        self.ii_forbid = integral(self.forbid)
        self.ii_notsal = integral(1.0 - self.sal)
        return self


def build_field(bgr, faces, matte, burn, face_pad=0.18, forbid_dilate=9) -> Field:
    h, w = bgr.shape[:2]
    facemask = np.zeros((h, w), np.float32)
    for f in faces:
        px, py = f.w * face_pad, f.h * face_pad
        x0 = int(max(0, f.x - px)); y0 = int(max(0, f.y - py))
        x1 = int(min(w, f.x + f.w + px)); y1 = int(min(h, f.y + f.h + py))
        facemask[y0:y1, x0:x1] = 1.0
    sal = np.maximum(matte, facemask)
    sal = np.maximum(sal, burn)
    forbid = (sal > 0.35).astype(np.uint8)
    if forbid_dilate:
        k = np.ones((forbid_dilate, forbid_dilate), np.uint8)
        forbid = cv2.dilate(forbid, k)
    people = ((matte > 0.5) | (burn > 0.5)).astype(np.float32)
    return Field(bgr=bgr, sal=sal, grad=grad_map(bgr), people=people,
                 forbid=forbid.astype(np.float32), faces=faces).bake()


# ---------------------------------------------------------------- placement --

def window_scores(fld: Field, bw: int, bh: int, step: int = 1):
    """Every bw x bh window at once. Returns (occ, rea, forbid_frac, ys, xs).

    occ  = mean sal under the window   -> PosterLayout metrics_occ, lower better
    rea  = mean grad under the window  -> PosterLayout metrics_rea, lower better
    """
    H, W = fld.sal.shape
    if bw >= W or bh >= H:
        return None
    ys = np.arange(0, H - bh + 1, step)
    xs = np.arange(0, W - bw + 1, step)
    Y0, X0 = np.meshgrid(ys, xs, indexing="ij")
    Y1, X1 = Y0 + bh, X0 + bw
    area = float(bw * bh)
    occ = rect_sum(fld.ii_sal, X0, Y0, X1, Y1) / area
    rea = rect_sum(fld.ii_grad, X0, Y0, X1, Y1) / area
    fbd = rect_sum(fld.ii_forbid, X0, Y0, X1, Y1) / area
    return occ, rea, fbd, ys, xs


def ali_penalty(boxes, W, H):
    """PosterLayout metrics_ali, ported verbatim from eval.py.

    Per element: min over the six channels (left, top, cx, cy, right, bottom)
    of -log10(1 - min_delta), where min_delta is the smallest normalised
    distance on that channel to any OTHER element. 0 = perfectly aligned.
    This is the number that measures "everything precisely placed next to each
    other" - the thing Nathan is actually complaining about.
    """
    if len(boxes) <= 1:
        return 0.0
    th = []
    for (xl, yl, xr, yr) in boxes:
        a, b, c, d = xl / W, yl / H, xr / W, yr / H
        th.append([a, b, (a + c) / 2, (b + d) / 2, c, d])
    th = np.array(th, dtype=np.float64)
    total = 0.0
    n = len(th)
    for i in range(n):
        gvals = []
        for j in range(6):
            col = th[:, j]
            deltas = np.abs(col[i] - np.delete(col, i))
            d = float(deltas.min())
            d = min(d, 0.999999)
            gvals.append(-math.log10(1.0 - d))
        total += min(gvals)
    return total


def utilisation(fld: Field, boxes):
    """PosterLayout metrics_uti: of all the non-salient pixels available, what
    fraction did the layout actually put an element on. Higher = the empty
    space is being used rather than left as dead air."""
    H, W = fld.sal.shape
    m = np.zeros((H, W), np.float32)
    for (xl, yl, xr, yr) in boxes:
        m[int(yl):int(yr), int(xl):int(xr)] = 1.0
    notsal = 1.0 - fld.sal
    tot = float(notsal.sum())
    if tot <= 0:
        return 0.0
    return float((notsal * m).sum() / tot)


def overlap_ratio(boxes):
    """PosterLayout metrics_ove: mean pairwise IoU."""
    n = len(boxes)
    if n < 2:
        return 0.0
    tot = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            ax0, ay0, ax1, ay1 = boxes[i]
            bx0, by0, bx1, by1 = boxes[j]
            iw = min(ax1, bx1) - max(ax0, bx0)
            ih = min(ay1, by1) - max(ay0, by0)
            inter = iw * ih if (iw > 0 and ih > 0) else 0.0
            a = (ax1 - ax0) * (ay1 - ay0)
            b = (bx1 - bx0) * (by1 - by0)
            tot += inter / (a + b - inter)
    return tot / n
