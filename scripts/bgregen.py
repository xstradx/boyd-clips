"""bgregen - regenerate the ROOM, never the person.

Nathan, 2026-08-29: *"maybe you could regenerate the backgrounds every time and
you will have full control over the lighting ofc because youre remaking it
yourself with the real reference"*.

His split is the right one. Measured on the 9,800-view Pikzels thumbnail: it
REGENERATES the person rather than upscaling them - Judge Boyd's eyes come back
bright blue where hers are brown, and her glasses change shape. Eye colour does
not vary between hearings, so that is diagnostic. Regenerating the ROOM buys the
lighting control that makes that reference look good; regenerating the PERSON
publishes an altered depiction of a sitting judge in a criminal proceeding, and
throws away the one structural advantage this channel has over the AI-slop
courtroom channels the practitioner community mocks by consensus.

So this module has exactly one hard invariant, and it is enforced by a test
rather than promised in a comment:

    EVERY PIXEL OF EVERY FACE IS BIT-IDENTICAL TO THE SOURCE FRAME.

selftest-faces-untouched asserts it. selftest-faces-control proves the assertion
can actually fail, by altering a face on purpose and requiring detection - an
absence check nobody has exercised against a positive control is worthless.

  python scripts/bgregen.py selftest-backend
  python scripts/bgregen.py selftest-faces-untouched
  python scripts/bgregen.py selftest-faces-control
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WORK = ROOT / "work" / "bgregen"
sys.path.insert(0, str(SCRIPTS))

# Where a local generation backend would live. Probed 2026-08-29: both are
# installed, ComfyUI has zero weights, and no SDXL/Flux/SD checkpoint exists
# anywhere on C: or D:. Fooocus's venv does have torch 2.10.0+cu128 with
# cuda True, so the GPU path is real once a checkpoint is present.
COMFY = Path(r"C:\Users\natha\AI-Tools\ComfyUI")
FOOOCUS = Path(r"C:\Users\natha\AI-Tools\Fooocus")

# Checkpoints live on D:. C: was at 94% and a 6.6 GB model has no business on
# the system drive when D: has 669 GB free.
CKPT_DIR = Path(r"D:\AI-Models\checkpoints")
# Generation runs under the Fooocus interpreter: the repo python is
# torch 2.13.0+cpu, Fooocus's venv is 2.10.0+cu128 with cuda True.
GEN_PY = FOOOCUS / "venv" / "Scripts" / "python.exe"


# ------------------------------------------------------------------ faces
def face_boxes(bgr):
    """Every face we can find, padded. Deliberately generous: a box that is too
    big only makes the invariant STRICTER, which is the safe direction."""
    casc = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    out = []
    h, w = g.shape
    for (x, y, fw, fh) in casc.detectMultiScale(g, 1.08, 5, minSize=(60, 60)):
        pad = int(fw * 0.30)
        out.append((max(0, x - pad), max(0, y - pad),
                    min(w, x + fw + pad), min(h, y + fh + pad)))
    return out


def faces_identical(src, out, alpha=None):
    """(ok, n_faces, max_abs_diff) over the PERSON pixels inside each face box.

    Corrected 2026-08-29 after this gate failed for the wrong reason. The first
    version compared the whole padded face box and reported max diff 240 on a
    correct composite - because a face box padded by 30% necessarily contains
    background, and background is exactly what we are replacing. Demanding that
    it stay identical made the invariant unsatisfiable, not strict.

    The meaningful invariant: inside a face box, every pixel WHERE THE PERSON IS
    OPAQUE must be bit-identical. Background pixels inside the box may change.
    A relight of the person's own skin still lands on opaque pixels, so this
    remains strict about the thing that matters - proven by
    selftest-faces-control, which alters one face by a single code value and
    must be caught.
    """
    if src.shape != out.shape:
        return False, 0, 255
    boxes = face_boxes(src)
    if alpha is None:
        alpha = people_alpha(src)
    worst, checked = 0, 0
    for (x0, y0, x1, y1) in boxes:
        a = src[y0:y1, x0:x1].astype(np.int16)
        b = out[y0:y1, x0:x1].astype(np.int16)
        m = alpha[y0:y1, x0:x1] > 0.995          # the person, not the room
        if not m.any():
            continue
        checked += int(m.sum())
        worst = max(worst, int(np.abs(a[m] - b[m]).max()))
    if checked == 0:
        return False, len(boxes), 255            # nothing verified is a failure
    return worst == 0, len(boxes), worst


# ------------------------------------------------------------------ matte
def people_alpha(bgr):
    """Alpha for the people, via the matting already proven in this repo.

    BiRefNet-portrait is MIT. rembg's DEFAULT model is BRIA RMBG-2.0, which is
    CC BY-NC 4.0 - NON-COMMERCIAL - and nothing in rembg warns you. Never call
    remove() here without naming a model.
    """
    from rembg import new_session, remove
    import io
    from PIL import Image
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("could not encode frame for matting")
    cut = remove(buf.tobytes(), session=new_session("birefnet-portrait"))
    img = Image.open(io.BytesIO(cut)).convert("RGBA")
    return np.asarray(img.getchannel("A"), dtype=np.float32) / 255.0


def compose(src_bgr, new_bg_bgr, alpha=None, feather=2.0):
    """Real people over a new room. The people's pixels are COPIED, never
    resampled or blended into - any interpolation here would alter a face by a
    code value or two and break the invariant for no visual gain."""
    if alpha is None:
        alpha = people_alpha(src_bgr)
    if new_bg_bgr.shape != src_bgr.shape:
        new_bg_bgr = cv2.resize(new_bg_bgr, (src_bgr.shape[1], src_bgr.shape[0]),
                                interpolation=cv2.INTER_LANCZOS4)
    a = alpha
    if feather > 0:
        a = cv2.GaussianBlur(a, (0, 0), feather)
    # hard-protect the interior so faces are copied verbatim, feather only the rim
    core = (alpha > 0.995).astype(np.float32)
    a = np.maximum(a, core)
    a3 = np.clip(a, 0.0, 1.0)[..., None]
    out = src_bgr.astype(np.float32) * a3 + new_bg_bgr.astype(np.float32) * (1 - a3)
    out = np.clip(out, 0, 255).astype(np.uint8)
    # belt and braces: stamp the fully-opaque region back in verbatim
    m = core.astype(bool)
    out[m] = src_bgr[m]
    return out


# --------------------------------------------------------------- selftests
def selftest_backend():
    """Report the generation backend honestly, including when there isn't one."""
    print("ComfyUI installed : %s" % COMFY.is_dir())
    print("Fooocus installed : %s" % FOOOCUS.is_dir())

    weights = []
    for base in (CKPT_DIR, COMFY / "models", FOOOCUS / "models"):
        if base.is_dir():
            for p in base.rglob("*"):
                if p.suffix.lower() in (".safetensors", ".ckpt", ".gguf") \
                        and p.stat().st_size > 500_000_000:
                    weights.append(p)
    print("generation checkpoints found: %d" % len(weights))
    for p in weights[:6]:
        print("   %5.1f GB  %s" % (p.stat().st_size / 1e9, p))

    cuda = None
    fpy = FOOOCUS / "venv" / "Scripts" / "python.exe"
    if fpy.is_file():
        import subprocess
        r = subprocess.run([str(fpy), "-c",
                            "import torch;print(torch.__version__,torch.cuda.is_available())"],
                           capture_output=True, text=True, timeout=180)
        cuda = r.stdout.strip()
        print("Fooocus torch     : %s" % (cuda or r.stderr.strip()[:80]))

    if not weights:
        print("\nNO GENERATION CHECKPOINT ON THIS MACHINE.")
        print("The infrastructure is here and GPU-capable, but there is nothing")
        print("to generate with. A checkpoint has to be downloaded first - that")
        print("is a free download, not a purchase. Until then this gate is")
        print("HONESTLY UNMET rather than worked around.")
        return 1
    if not (cuda and "True" in cuda):
        print("\nbackend present but CUDA unavailable - would run on CPU")
        return 1
    print("BACKEND_READY")
    return 0


def _demo_frame():
    """A real courtroom frame with real faces in it."""
    for c in (ROOT / "work/repair/smoke.jpg",
              ROOT / "research/reference/ttt_own/cSz-vkSwVlk.jpg"):
        if c.is_file():
            img = cv2.imread(str(c))
            if img is not None:
                return img, c
    raise SystemExit("no demo frame available")


def selftest_faces_untouched():
    src, path = _demo_frame()
    print("frame: %s  %dx%d" % (path.name, src.shape[1], src.shape[0]))
    boxes = face_boxes(src)
    if not boxes:
        print("NO FACES DETECTED - the invariant would be vacuously true, which")
        print("is worse than failing. Refusing to pass.")
        return 1
    print("faces detected: %d" % len(boxes))

    # a deliberately violent background swap: flat magenta, nothing subtle
    bg = np.zeros_like(src)
    bg[:, :] = (200, 0, 200)
    WORK.mkdir(parents=True, exist_ok=True)
    alpha = people_alpha(src)
    out = compose(src, bg, alpha=alpha)
    cv2.imwrite(str(WORK / "faces_untouched.png"), out)

    ok, n, worst = faces_identical(src, out, alpha)
    print("after a full background replacement: %d faces, max abs pixel diff %d"
          % (n, worst))
    if not ok:
        print("FAILED - the composite altered face pixels")
        return 1
    print("FACES_BIT_IDENTICAL")
    return 0


def selftest_faces_control():
    """The check must FAIL on an alteration, or it proves nothing.

    An absence check that has never been exercised against a known positive is
    not evidence. This alters exactly one face by the smallest amount that
    should still be caught, and requires detection.
    """
    src, path = _demo_frame()
    boxes = face_boxes(src)
    if not boxes:
        print("no faces to alter - cannot run the control")
        return 1

    alpha = people_alpha(src)
    tampered = src.copy()
    # Alter a pixel the PERSON actually occupies - altering background inside
    # the box would no longer be caught, and correctly so.
    target = None
    for (x0, y0, x1, y1) in boxes:
        m = alpha[y0:y1, x0:x1] > 0.995
        if m.any():
            target = (x0, y0, x1, y1, m)
            break
    if target is None:
        print("no opaque person pixels inside any face box - cannot run control")
        return 1
    x0, y0, x1, y1, m = target
    # +1 code value on ONE channel, the subtlest possible alteration. If the
    # checker misses this it will miss a relight.
    region = tampered[y0:y1, x0:x1].astype(np.int16)
    region[:, :, 1] = np.where(m, np.clip(region[:, :, 1] + 1, 0, 255),
                               region[:, :, 1])
    tampered[y0:y1, x0:x1] = region.astype(np.uint8)

    ok, n, worst = faces_identical(src, tampered, alpha)
    print("altered one face by +1 on a single channel; checker saw max diff %d"
          % worst)
    if ok:
        print("CONTROL FAILED - the checker did not notice an altered face.")
        print("Every FACES_BIT_IDENTICAL pass is therefore meaningless.")
        return 1
    # and the negative control: an untouched copy must still pass
    ok2, _, worst2 = faces_identical(src, src.copy(), alpha)
    if not ok2:
        print("CONTROL FAILED - an identical copy was reported as altered "
              "(max diff %d)" % worst2)
        return 1
    print("identical copy still passes (max diff %d)" % worst2)
    print("CONTROL_DETECTED_ALTERATION")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest-backend")
    sub.add_parser("selftest-faces-untouched")
    sub.add_parser("selftest-faces-control")
    a = ap.parse_args()
    return {"selftest-backend": selftest_backend,
            "selftest-faces-untouched": selftest_faces_untouched,
            "selftest-faces-control": selftest_faces_control}[a.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())
