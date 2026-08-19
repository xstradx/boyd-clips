# -*- coding: utf-8 -*-
import io, os, re, sys
SUB = r"research/reference/courtroomtime/subs"
OUT = r"research/reference/courtroomtime/txt"
os.makedirs(OUT, exist_ok=True)
ts_re = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d\d\d) --> ")
tag_re = re.compile(r"<[^>]+>")

def conv(path):
    lines = io.open(path, encoding='utf-8', errors='replace').read().split('\n')
    out = []
    cur_t = 0
    seen_tail = ""
    for ln in lines:
        m = ts_re.match(ln.strip())
        if m:
            cur_t = int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
            continue
        s = tag_re.sub('', ln).strip()
        if not s or s.startswith('WEBVTT') or s.startswith('Kind:') or s.startswith('Language:') or s.startswith('NOTE'):
            continue
        if s == seen_tail:
            continue
        # rolling caption: new text is often previous line + extra
        if seen_tail and s.startswith(seen_tail):
            s = s[len(seen_tail):].strip()
            if not s: continue
        out.append((cur_t, s))
        seen_tail = tag_re.sub('', ln).strip()
    # merge into ~ lines
    merged = []
    buf = []
    t0 = 0
    for t, s in out:
        if not buf:
            t0 = t
        buf.append(s)
        if sum(len(x) for x in buf) > 110:
            merged.append((t0, ' '.join(buf)))
            buf = []
    if buf:
        merged.append((t0, ' '.join(buf)))
    return merged

for f in sorted(os.listdir(SUB)):
    if not f.endswith('.vtt'): continue
    vid = f.split('.')[0]
    m = conv(os.path.join(SUB, f))
    with io.open(os.path.join(OUT, vid + '.txt'), 'w', encoding='utf-8') as fh:
        for t, s in m:
            fh.write("[%02d:%02d] %s\n" % (t//60, t%60, s))
    print(vid, len(m), 'lines')
