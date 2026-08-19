"""Parse YouTube auto-sub VTT into clean text + word list, and load labels."""
import os, re, io, json, html

TAG = re.compile(r"<[^>]*>")
CUE = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d\d\d) --> ")
WORDT = re.compile(r"<(\d\d):(\d\d):(\d\d)\.(\d\d\d)><c>([^<]*)</c>")


def parse_vtt(path):
    """Return (text, words) where words = [(t, token)].

    YouTube auto-subs roll: each cue repeats the previous cue's tail on its
    first line(s) and puts NEW words on the last line, tagged with per-word
    timings. Taking only the last payload line of cues that carry <c> tags
    reconstructs the transcript exactly once.
    """
    raw = io.open(path, encoding="utf-8", errors="replace").read()
    blocks = re.split(r"\n\n+", raw)
    words, chunks = [], []
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip()]
        if not lines:
            continue
        m = CUE.match(lines[0].strip())
        if not m:
            continue
        t0 = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
        payload = lines[1:]
        if not payload:
            continue
        last = payload[-1]
        if "<c>" not in last:
            continue
        lead = last.split("<", 1)[0]
        seg = html.unescape(TAG.sub("", last)).strip()
        if not seg:
            continue
        chunks.append(seg)
        t = t0
        if lead.strip():
            words.append((t0, html.unescape(lead.strip())))
        for wm in WORDT.finditer(last):
            t = int(wm.group(1)) * 3600 + int(wm.group(2)) * 60 + int(wm.group(3)) + int(wm.group(4)) / 1000
            tok = html.unescape(wm.group(5)).strip()
            if tok:
                words.append((t, tok))
    return " ".join(chunks), words


def load(root="research/reference/courtroomtime", flat="ct_flat.txt"):
    meta = {}
    for l in io.open(flat, encoding="utf-8-sig"):
        p = l.rstrip("\n").split("|")
        if len(p) >= 4 and p[1].isdigit():
            meta[p[0]] = dict(id=p[0], views=int(p[1]), dur=int(p[2]), title=p[3])
    docs = []
    sub = os.path.join(root, "subs")
    for f in sorted(os.listdir(sub)):
        if not f.endswith(".vtt"):
            continue
        vid = f.split(".")[0]
        if vid not in meta:
            continue
        text, words = parse_vtt(os.path.join(sub, f))
        nw = len(text.split())
        if nw < 500:
            continue
        d = dict(meta[vid])
        d["text"] = text
        d["words"] = words
        d["nwords"] = nw
        docs.append(d)
    return docs
