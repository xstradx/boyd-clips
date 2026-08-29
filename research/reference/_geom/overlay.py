# -*- coding: utf-8 -*-
import json, os, glob, math
import numpy as np, cv2

GEO = 'C:/Users/natha/Projects/boyd-clips/research/reference/_geom'
ROOT = 'C:/Users/natha/Projects/boyd-clips/research/reference'
G = json.load(open(GEO + '/geom.json'))
os.makedirs(GEO + '/ov', exist_ok=True)
src = {os.path.basename(p): p for p in
       glob.glob(ROOT + '/competitor/thumbs/*.jpg') + glob.glob(ROOT + '/courtroomtime/thumbs/*.jpg')}

for base, d in G.items():
    im = cv2.imread(src[base])
    ov = im.copy()
    mp = GEO + '/mattes/' + base[:-4] + '.png'
    if os.path.exists(mp):
        mk = cv2.imread(mp, 0) > 128
        e = cv2.Canny((mk * 255).astype(np.uint8), 50, 150)
        ov[e > 0] = (255, 0, 255)
    er = d['empty_all']
    cv2.rectangle(ov, (er['x'], er['y']), (er['x'] + er['w'], er['y'] + er['h']), (0, 255, 255), 3)
    cv2.putText(ov, 'EMPTY', (er['x'] + 6, er['y'] + 26), 0, 0.8, (0, 255, 255), 2)
    for f in d['faces']:
        cv2.rectangle(ov, (int(f['x']), int(f['y'])), (int(f['x'] + f['w']), int(f['y'] + f['h'])), (0, 255, 0), 3)
        cv2.putText(ov, "h%d" % f['h'], (int(f['x']), max(14, int(f['y']) - 6)), 0, 0.6, (0, 255, 0), 2)
    for t in d['text']:
        cv2.rectangle(ov, (int(t['x0']), int(t['y0'])), (int(t['x1']), int(t['y1'])), (255, 255, 0), 2)
        cv2.putText(ov, "cap%d" % t['cap'], (int(t['x0']), int(t['y1']) + 20), 0, 0.6, (255, 255, 0), 2)
        for col, a, b in t['runs']:
            c = {'white': (255, 255, 255), 'yellow': (0, 200, 255), 'red': (0, 0, 255), 'black': (40, 40, 40)}[col]
            cv2.line(ov, (int(a), int(t['y1']) + 4), (int(b), int(t['y1']) + 4), c, 4)
    for a in d['accents']:
        col = {'arrow': (255, 0, 255), 'bar': (0, 140, 255), 'shape': (255, 120, 0), 'frame': (128, 128, 128)}[a['kind']]
        cv2.rectangle(ov, (a['x'], a['y']), (a['x'] + a['w'], a['y'] + a['h']), col, 2)
        cv2.putText(ov, a['kind'] + str(a['area']), (a['x'], max(14, a['y'] - 6)), 0, 0.55, col, 2)
        if a['kind'] == 'arrow':
            cv2.circle(ov, (int(a['tip'][0]), int(a['tip'][1])), 9, (255, 255, 255), -1)
            cv2.circle(ov, (int(a['tip'][0]), int(a['tip'][1])), 9, col, 2)
            r = math.radians(a['ang'])
            cv2.arrowedLine(ov, (int(a['cx']), int(a['cy'])),
                            (int(a['cx'] + 90 * math.cos(r)), int(a['cy'] + 90 * math.sin(r))), col, 4, tipLength=.3)
    cv2.imwrite(GEO + '/ov/' + base[:-4] + '.png', ov)

names = sorted(G.keys())
for si in range(0, len(names), 6):
    chunk = names[si:si + 6]
    tiles = []
    for n in chunk:
        t = cv2.resize(cv2.imread(GEO + '/ov/' + n[:-4] + '.png'), (640, 360))
        cv2.putText(t, n[:26], (6, 350), 0, 0.6, (0, 0, 0), 4)
        cv2.putText(t, n[:26], (6, 350), 0, 0.6, (255, 255, 255), 1)
        tiles.append(t)
    while len(tiles) < 6:
        tiles.append(np.zeros((360, 640, 3), np.uint8))
    sheet = np.vstack([np.hstack(tiles[0:2]), np.hstack(tiles[2:4]), np.hstack(tiles[4:6])])
    cv2.imwrite(GEO + '/sheet_%d.png' % (si // 6), sheet)
print('ok', len(names))
