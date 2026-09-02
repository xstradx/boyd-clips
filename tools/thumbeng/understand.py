# -*- coding: utf-8 -*-
"""What is this video, and what niche does it compete in? Stage 2 of 6.

This is the stage that makes the product real. The creator supplies NOTHING -
no niche, no brief, no idea. The engine has to look at the video and work out
what it is, the way a person who knows YouTube would.

Runs on a local vision model through Ollama, so the whole engine works offline
and costs nothing per call. The model is asked for STRICT JSON and the output
is validated - a model that free-forms here poisons every downstream stage.

What it must produce, and why each field earns its place:
  niche          human-readable, for the report
  search_query   THE LOAD-BEARING FIELD. This is what gets typed into YouTube
                 to find who this video is actually competing against. If this
                 is wrong, every competitor measured downstream is wrong, and
                 the engine confidently builds for the wrong feed.
  hook           the single most clickable fact in the video, in the creator's
                 own subject matter. Not a summary.
  headline       <= 5 words, what goes ON the thumbnail
  subject        who or what the picture should be OF
  emotion        the expression to look for when picking the frame
"""
import os, json, base64, urllib.request, urllib.error

def _ollama_base():
    """OLLAMA_HOST on this machine is '0.0.0.0' - a bind address for the server,
    not a URL a client can call. Normalise rather than crash on it: add the
    scheme, add the default port, and turn the wildcard bind into loopback."""
    h = (os.environ.get("OLLAMA_HOST") or "").strip() or "127.0.0.1:11434"
    if "://" not in h:
        h = "http://" + h
    from urllib.parse import urlsplit, urlunsplit
    p = urlsplit(h)
    host = p.hostname or "127.0.0.1"
    if host in ("0.0.0.0", "::", "[::]"):
        host = "127.0.0.1"
    port = p.port or 11434
    return urlunsplit((p.scheme or "http", f"{host}:{port}", "", "", ""))


OLLAMA = _ollama_base()
MODEL = os.environ.get("TE_VISION_MODEL", "qwen3-vl:8b")

SCHEMA_HINT = """Return ONLY a JSON object, no prose, with exactly these keys:
{"niche": str, "search_query": str, "hook": str, "headline": str,
 "subject": str, "emotion": str, "why": str}

Rules:
- search_query is what a viewer would TYPE INTO YOUTUBE to find videos like
  this one. 3-7 words. It decides which channels this video competes with, so
  it must describe the CONTENT CATEGORY, never this specific video's details.
  Good: "courtroom judge sentencing" / "minecraft story animation" /
  "car detailing satisfying". Bad: "Thompson hearing March 7".
- headline is AT MOST 5 words, upper or mixed case, no quotes, no emoji. It is
  printed on the image, so it must read at a glance.
- emotion is one word describing the face to look for: angry, shocked,
  laughing, crying, smug, deadpan, terrified.
- If the video has no people, subject is the thing the picture is of.
- why is one sentence explaining the search_query choice."""


class Unclear(Exception):
    pass


def _ollama(prompt, images=None, model=None, timeout=300):
    body = {"model": model or MODEL, "prompt": prompt, "stream": False,
            "format": "json", "think": False,
            "options": {"temperature": 0.2, "num_ctx": 8192}}
    if images:
        body["images"] = images
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate", method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
        # Qwen3 is a THINKING model: with think enabled it returns the answer in
        # `thinking` and leaves `response` empty. Measured on this machine -
        # a probe asking for {"ok":true} came back response:"" thinking:"{...}".
        # think:False is requested above; the fallback covers a build that
        # ignores the flag, so a silently-empty answer can never be mistaken
        # for a model that had nothing to say.
        return (d.get("response") or "").strip() or (d.get("thinking") or "").strip()
    except urllib.error.URLError as e:
        raise Unclear(
            f"cannot reach Ollama at {OLLAMA} ({e}). The engine will not guess a "
            f"niche from filename or folder - that is how it silently becomes a "
            f"single-niche script.")


def _b64(path, max_side=768):
    import cv2
    im = cv2.imread(path)
    h, w = im.shape[:2]
    k = max_side / float(max(h, w))
    if k < 1:
        im = cv2.resize(im, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf.tobytes()).decode("ascii")


REQUIRED = ("niche", "search_query", "hook", "headline", "subject", "emotion")


def run(work_dir, model=None, n_images=4):
    with open(os.path.join(work_dir, "ingest.json"), encoding="utf-8") as f:
        doc = json.load(f)

    text = " ".join(r["t"] for r in doc["transcript"])[:6000]
    imgs = [_b64(fr["path"]) for fr in doc["frames"][:n_images]
            if os.path.exists(fr["path"])]

    prompt = (
        "You are a YouTube packaging strategist. You are shown frames from a "
        "video and part of its transcript. Work out what KIND of video this is "
        "and what it competes against.\n\n"
        f"TRANSCRIPT (may be empty):\n{text if text else '(no speech)'}\n\n"
        f"{SCHEMA_HINT}")

    raw = _ollama(prompt, images=imgs, model=model)
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        raise Unclear(f"model did not return JSON: {raw[:300]}")

    missing = [k for k in REQUIRED if not str(out.get(k, "")).strip()]
    if missing:
        raise Unclear(f"model omitted required fields: {missing}")

    q = " ".join(str(out["search_query"]).split())
    if not (2 <= len(q.split()) <= 9):
        raise Unclear(f"search_query is not a usable YouTube query: {q!r}")
    out["search_query"] = q
    out["headline"] = " ".join(str(out["headline"]).split())[:60]
    if len(out["headline"].split()) > 6:
        out["headline"] = " ".join(out["headline"].split()[:5])
    out["model"] = model or MODEL

    with open(os.path.join(work_dir, "understand.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    return out
