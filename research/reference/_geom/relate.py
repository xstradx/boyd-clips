# -*- coding: utf-8 -*-
"""Per-file layout RELATIONSHIPS + corpus distributions, from geom.json."""
import json, os, math, io
import numpy as np, cv2

GEO = 'C:/Users/natha/Projects/boyd-clips/research/reference/_geom'
G = json.load(open(GEO + '/geom.json'))


def rectgap(a, b):
    """centre-free gap between two rects (x0,y0,x1,y1); 0 if they overlap"""
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy), dx, dy


import sys
sys.path.insert(0, GEO)
from measure import graphic_masks
SRC = {}
import glob
for p in glob.glob('C:/Users/natha/Projects/boyd-clips/research/reference/competitor/thumbs/*.jpg') + \
         glob.glob('C:/Users/natha/Projects/boyd-clips/research/reference/courtroomtime/thumbs/*.jpg'):
    SRC[os.path.basename(p)] = p


def _shape_mask(d, a, H, W):
    """recover the arrow's actual pixel mask (not its bbox) for on-person counting"""
    im = cv2.imread(SRC[d['_base']])
    m = graphic_masks(im)[a['colour']]
    m = cv2.morphologyEx(m.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
    reg = np.zeros((H, W), bool)
    reg[a['y']:a['y'] + a['h'], a['x']:a['x'] + a['w']] = True
    mm = (m & reg).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mm, 8)
    if n < 2:
        return np.zeros((H, W), bool)
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return lab == i


def blocks(lines):
    """group text lines into blocks by vertical proximity + horizontal overlap"""
    out = []
    for L in sorted(lines, key=lambda d: d['y0']):
        placed = False
        for B in out:
            last = B[-1]
            vg = L['y0'] - last['y1']
            ox = min(L['x1'], last['x1']) - max(L['x0'], last['x0'])
            narrow = min(L['x1'] - L['x0'], last['x1'] - last['x0'])
            if vg < 0.95 * max(L['cap'], last['cap']) and ox > 0.18 * narrow:
                B.append(L)
                placed = True
                break
        if not placed:
            out.append([L])
    return out


rows = []
for base, d in sorted(G.items()):
    d['_base'] = base
    W, H = d['W'], d['H']
    corp = 'AUDIT' if not base.startswith(('top_', 'bot_')) else ('CT_TOP' if base.startswith('top_') else 'CT_BOT')
    views = int(base.split('_')[0]) if corp == 'AUDIT' else int(base.split('_')[1])
    mk = cv2.imread(GEO + '/mattes/' + base[:-4] + '.png', 0)
    matte = (mk > 128) if mk is not None else np.zeros((H, W), bool)

    F = [f for f in d['faces'] if f['h'] >= 0.12 * H]
    F.sort(key=lambda f: -(f['w'] * f['h']))
    BL = blocks(d['text'])
    BL.sort(key=lambda B: -sum((l['x1'] - l['x0']) * (l['y1'] - l['y0']) for l in B))
    AR = [a for a in d['accents'] if a['kind'] == 'arrow']
    AR.sort(key=lambda a: -a['area'])

    r = dict(file=base, corpus=corp, views=views, W=W, H=H, nface=len(F), nblock=len(BL), narrow=len(AR))

    # ---- faces
    for i, f in enumerate(F[:2]):
        r['f%d_cx' % (i + 1)] = (f['x'] + f['w'] / 2) / W
        r['f%d_cy' % (i + 1)] = (f['y'] + f['h'] / 2) / H
        r['f%d_h' % (i + 1)] = f['h'] / H
        r['f%d_x0' % (i + 1)] = f['x'] / W
        r['f%d_x1' % (i + 1)] = (f['x'] + f['w']) / W
        r['f%d_y0' % (i + 1)] = f['y'] / H
        r['f%d_y1' % (i + 1)] = (f['y'] + f['h']) / H
    if len(F) >= 2:
        a, b = F[0], F[1]
        acx, acy = (a['x'] + a['w'] / 2), (a['y'] + a['h'] / 2)
        bcx, bcy = (b['x'] + b['w'] / 2), (b['y'] + b['h'] / 2)
        r['ff_dx'] = abs(acx - bcx) / W
        r['ff_dy'] = abs(acy - bcy) / H
        r['ff_d'] = math.hypot(acx - bcx, acy - bcy) / W
        r['ff_d_over_h'] = math.hypot(acx - bcx, acy - bcy) / ((a['h'] + b['h']) / 2)
        r['ff_hratio'] = a['h'] / b['h']
        r['ff_eyelevel_dy'] = abs(acy - bcy) / H
        r['ff_gap'] = rectgap((a['x'], a['y'], a['x'] + a['w'], a['y'] + a['h']),
                              (b['x'], b['y'], b['x'] + b['w'], b['y'] + b['h']))[1] / W
        r['ff_midx'] = ((acx + bcx) / 2) / W
        # do they face each other? nose vs eye-midpoint gives gaze side
        for tag, ff in (('f1', a), ('f2', b)):
            ex = (ff['lm'][0][0] + ff['lm'][1][0]) / 2
            r[tag + '_gaze'] = (ff['lm'][2][0] - ex) / ff['w']   # + = looking right

    # ---- text block (largest)
    if BL:
        B = BL[0]
        x0 = min(l['x0'] for l in B); x1 = max(l['x1'] for l in B)
        y0 = min(l['y0'] for l in B); y1 = max(l['y1'] for l in B)
        r.update(t_x0=x0 / W, t_x1=x1 / W, t_y0=y0 / H, t_y1=y1 / H,
                 t_w=(x1 - x0) / W, t_h=(y1 - y0) / H, t_lines=len(B),
                 t_cap=float(np.median([l['cap'] for l in B])) / H,
                 t_cap_px=float(np.median([l['cap'] for l in B])),
                 t_cx=((x0 + x1) / 2) / W, t_cy=((y0 + y1) / 2) / H,
                 t_left_in=x0 / W, t_right_in=(W - x1) / W,
                 t_top_in=y0 / H, t_bot_in=(H - y1) / H,
                 t_pol=B[0].get('polarity', '?'))
        if len(B) > 1:
            ys = sorted(l['y0'] for l in B)
            r['t_pitch'] = float(np.median(np.diff(ys))) / r['t_cap_px']
            r['t_leftvar'] = float(np.std([l['x0'] for l in B])) / W
        # words on a person?
        tmask = np.zeros((H, W), bool)
        for l in B:
            tmask[max(0, int(l['y0'])):int(l['y1']), max(0, int(l['x0'])):int(l['x1'])] = True
        r['t_on_matte'] = float((tmask & matte).sum()) / max(1, tmask.sum())
        fmask = np.zeros((H, W), bool)
        for f in d['faces']:
            fmask[max(0, int(f['y'])):int(f['y'] + f['h']), max(0, int(f['x'])):int(f['x'] + f['w'])] = True
        r['t_on_face'] = float((tmask & fmask).sum()) / max(1, tmask.sum())
        r['t_on_person'] = float((tmask & (matte | fmask)).sum()) / max(1, tmask.sum())
        # gap to each face + alignment
        gaps = []
        for f in F:
            g = rectgap((x0, y0, x1, y1), (f['x'], f['y'], f['x'] + f['w'], f['y'] + f['h']))
            gaps.append(g[0] / W)
        if gaps:
            r['t_face_gap'] = min(gaps)
        # alignment tests (tolerance 1.5% of W / H)
        tolx, toly = 0.015 * W, 0.015 * H
        r['t_align_frameL'] = bool(x0 < 0.06 * W)
        r['t_align_frameR'] = bool((W - x1) < 0.06 * W)
        r['t_align_frameT'] = bool(y0 < 0.06 * H)
        r['t_align_frameB'] = bool((H - y1) < 0.06 * H)
        al = []
        for i, f in enumerate(F[:2]):
            for enm, ev in (('L', f['x']), ('R', f['x'] + f['w']), ('C', f['x'] + f['w'] / 2)):
                if abs(x0 - ev) < tolx: al.append('t.x0~f%d.%s' % (i + 1, enm))
                if abs(x1 - ev) < tolx: al.append('t.x1~f%d.%s' % (i + 1, enm))
            for enm, ev in (('T', f['y']), ('B', f['y'] + f['h']), ('M', f['y'] + f['h'] / 2)):
                if abs(y0 - ev) < toly: al.append('t.y0~f%d.%s' % (i + 1, enm))
                if abs(y1 - ev) < toly: al.append('t.y1~f%d.%s' % (i + 1, enm))
        r['t_align_face'] = ';'.join(al)
        # which side is the text on vs the biggest face
        if F:
            r['t_side_vs_f1'] = 'same' if (r['t_cx'] < .5) == ((F[0]['x'] + F[0]['w'] / 2) / W < .5) else 'opp'

    # ---- arrow
    if AR:
        a = AR[0]
        r.update(a_x0=a['x'] / W, a_y0=a['y'] / H, a_w=a['w'] / W, a_h=a['h'] / H,
                 a_area=a['area'] / float(W * H), a_cx=a['cx'] / W, a_cy=a['cy'] / H,
                 a_ang=a['ang'], a_tipx=a['tip'][0] / W, a_tipy=a['tip'][1] / H,
                 a_colour=a['colour'])
        am = np.zeros((H, W), bool)
        am[a['y']:a['y'] + a['h'], a['x']:a['x'] + a['w']] = True
        r['a_bbox_on_matte'] = float((am & matte).sum()) / max(1, am.sum())
        # ray-cast from the tip along the heading: how far to the first person pixel
        fmask = np.zeros((H, W), bool)
        for f in d['faces']:
            fmask[max(0, int(f['y'])):int(f['y'] + f['h']), max(0, int(f['x'])):int(f['x'] + f['w'])] = True
        person = matte | fmask
        th = math.radians(a['ang'])
        hit = None
        for s in range(0, int(1.5 * W)):
            px = int(a['tip'][0] + s * math.cos(th)); py = int(a['tip'][1] + s * math.sin(th))
            if not (0 <= px < W and 0 <= py < H):
                break
            if person[py, px]:
                hit = s
                break
        r['a_ray_to_person'] = (hit / float(W)) if hit is not None else -1.0
        r['a_hits_person'] = bool(hit is not None)
        # clear space in front of the tip: radius of the largest empty disc at the tip
        dt = cv2.distanceTransform((~person).astype(np.uint8), cv2.DIST_L2, 5)
        tx, ty = int(np.clip(a['tip'][0], 0, W - 1)), int(np.clip(a['tip'][1], 0, H - 1))
        r['a_tip_clearance'] = float(dt[ty, tx]) / W
        cxi, cyi = int(np.clip(a['cx'], 0, W - 1)), int(np.clip(a['cy'], 0, H - 1))
        r['a_body_clearance'] = float(dt[cyi, cxi]) / W
        r['a_on_person_px'] = float((_shape_mask(d, a, H, W) & person).sum()) / max(1, a['area'])
        # which face is it aimed at: smallest angular error from tip along heading
        best = None
        for i, f in enumerate(F):
            fcx, fcy = f['x'] + f['w'] / 2, f['y'] + f['h'] / 2
            v = math.degrees(math.atan2(fcy - a['tip'][1], fcx - a['tip'][0]))
            err = abs((v - a['ang'] + 180) % 360 - 180)
            dist = math.hypot(fcx - a['tip'][0], fcy - a['tip'][1]) / W
            if best is None or err < best[0]:
                best = (err, i + 1, dist)
        if best:
            r['a_aim_err_deg'] = best[0]; r['a_aim_face'] = best[1]; r['a_tip_face_d'] = best[2]
        if BL:
            B = BL[0]
            x0 = min(l['x0'] for l in B); x1 = max(l['x1'] for l in B)
            y0 = min(l['y0'] for l in B); y1 = max(l['y1'] for l in B)
            r['a_text_gap'] = rectgap((a['x'], a['y'], a['x'] + a['w'], a['y'] + a['h']),
                                      (x0, y0, x1, y1))[0] / W

    # ---- empty
    for tag in ('empty_all', 'empty_elem'):
        e = d[tag]
        p = 'e_' if tag == 'empty_all' else 'ee_'
        r[p + 'x'] = e['x'] / W; r[p + 'y'] = e['y'] / H
        r[p + 'w'] = e['w'] / W; r[p + 'h'] = e['h'] / H
        r[p + 'area'] = e['area'] / float(W * H)
        r[p + 'cx'] = (e['x'] + e['w'] / 2) / W; r[p + 'cy'] = (e['y'] + e['h'] / 2) / H
    r['matte_cov'] = float(matte.mean())
    rows.append(r)

json.dump(rows, open(GEO + '/relate.json', 'w'), indent=1)


def dist(key, sub=None, fmt='%.3f'):
    v = [r[key] for r in rows if key in r and (sub is None or r['corpus'] in sub)]
    if not v:
        return key, 0, None
    v = np.array(v, float)
    return key, len(v), (np.median(v), np.percentile(v, 25), np.percentile(v, 75), v.min(), v.max(),
                         float(np.std(v) / (abs(np.mean(v)) + 1e-9)))


KEYS = ['f1_cx', 'f1_cy', 'f1_h', 'f2_cx', 'f2_cy', 'f2_h', 'ff_dx', 'ff_dy', 'ff_d', 'ff_d_over_h',
        'ff_hratio', 'ff_eyelevel_dy', 'ff_gap', 'ff_midx',
        't_x0', 't_x1', 't_y0', 't_y1', 't_w', 't_h', 't_cap', 't_cap_px', 't_cx', 't_cy',
        't_left_in', 't_right_in', 't_top_in', 't_bot_in', 't_pitch', 't_leftvar', 't_on_matte', 't_face_gap',
        't_on_face', 't_on_person',
        'a_area', 'a_cx', 'a_cy', 'a_tipx', 'a_tipy', 'a_aim_err_deg', 'a_tip_face_d', 'a_text_gap',
        'a_bbox_on_matte', 'a_on_person_px', 'a_ray_to_person', 'a_tip_clearance', 'a_body_clearance', 'e_area', 'e_cx', 'e_cy', 'ee_area', 'ee_cx', 'ee_cy', 'matte_cov']
print('%-16s %-8s %8s %8s %8s %8s %8s %6s' % ('key', 'corpus', 'median', 'q25', 'q75', 'min', 'max', 'CV'))
for k in KEYS:
    for sub, nm in ((None, 'ALL'), (('AUDIT',), 'AUDIT'), (('CT_TOP', 'CT_BOT'), 'CT'),
                    (('CT_TOP',), 'CT_TOP'), (('CT_BOT',), 'CT_BOT')):
        kk, n, s = dist(k, sub)
        if s is None:
            continue
        print('%-16s %-8s %8.4f %8.4f %8.4f %8.4f %8.4f %6.2f  n=%d' % (k, nm, s[0], s[1], s[2], s[3], s[4], s[5], n))
    print()
