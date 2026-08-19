"""Implementation C: pure ffmpeg. Same lower third as bakeoff_spec.

    python bakeoff_ffmpeg.py [outdir]

Four ffmpeg facts this had to be built around, each MEASURED here, not assumed:

1. drawbox NEVER writes alpha. On a transparent rgba (or argb) source it blends
   the colour into RGB and leaves the alpha plane at 0 - so the box is invisible
   in the delivered PNG while looking perfectly fine if you preview it on black.
   Measured: px(200,100) = #D42B2B at alpha 0, max alpha over the whole frame 0.
   Every plate here is therefore a `color` source composited with `overlay`,
   which does write alpha (measured 237 for @0.93).

2. drawtext DOES write alpha, and antialiases well - 133 distinct alpha levels
   on a single word.

3. There is no letter-spacing option in drawtext. Tracking has to be done with
   ONE drawtext FILTER PER CHARACTER, with the advance widths computed outside
   ffmpeg. The charge line is 27 characters, so it is 27 chained filters.

4. crop cannot animate its width (w/h are evaluated once at configuration
   time), so a wipe cannot be a crop. It has to be geq rewriting the alpha
   plane per pixel: a='alpha(X,Y)*lt(X,<edge expr>)'. That is the direct
   analogue of the shader threshold, and it is where the render time goes.

5. overlay DEFAULTS TO A YUV FORMAT and silently shifts brand colours. Measured
   without format=rgb: red delivered as #D3292A instead of #D42B2B and ink as
   #F1ECE0 instead of #F2EEE3. This is ffmpeg's exact analogue of Blender's AgX
   default - a colour-management default that quietly breaks brand accuracy.

Easing is easeOutCubic written out as an arithmetic expression, because ffmpeg
cannot evaluate an arbitrary cubic bezier.
"""
import os
import subprocess
import sys
import time

from PIL import ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bakeoff_spec as S

HERE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = r"C:\ffmpeg\ffmpeg.exe"


def esc(path):
    """ffmpeg filter-arg escaping for a Windows path."""
    return path.replace("\\", "/").replace(":", "\\:")


def ramp(f0, f1, v0, v1):
    u = "clip((N+1-%g)/%g,0,1)" % (f0, float(f1 - f0))
    return "(%g+(%g)*(1-pow(1-%s,3)))" % (v0, v1 - v0, u)


E1 = "if(lt(N+1,%g),%s,%s)" % (
    S.F_OUT, ramp(S.F_T1[0], S.F_T1[1], S.CLOSED, S.X0 + S.W1),
    ramp(S.F_OUT, S.F_OUT + S.FADE_OUT, S.X0 + S.W1, S.CLOSED))
E1T = "if(lt(N+1,%g),%s,%s)" % (
    S.F_OUT, ramp(S.F_T1[0], S.F_T1[1], S.CLOSED - S.LEAD, S.X0 + S.W1 - S.LEAD),
    ramp(S.F_OUT, S.F_OUT + S.FADE_OUT, S.X0 + S.W1 - S.LEAD, S.CLOSED - S.LEAD))
E2 = "if(lt(N+1,%g),%s,%s)" % (
    S.F_OUT - 3, ramp(S.F_T2[0], S.F_T2[1], S.CLOSED, S.X0 + S.W2),
    ramp(S.F_OUT - 3, S.F_OUT - 3 + S.FADE_OUT, S.X0 + S.W2, S.CLOSED))
E2T = "if(lt(N+1,%g),%s,%s)" % (
    S.F_OUT - 3, ramp(S.F_T2[0], S.F_T2[1], S.CLOSED - S.LEAD, S.X0 + S.W2 - S.LEAD),
    ramp(S.F_OUT - 3, S.F_OUT - 3 + S.FADE_OUT, S.X0 + S.W2 - S.LEAD, S.CLOSED - S.LEAD))
_BOT = S.T1_TOP + S.T1_H + S.T2_H
ER = "if(lt(N+1,%g),%s,%s)" % (
    S.F_OUT + 4, ramp(S.F_RULE[0], S.F_RULE[1], S.T1_TOP, _BOT),
    ramp(S.F_OUT + 4, S.F_OUT + S.FADE_OUT, _BOT, S.T1_TOP))


def clip_x(expr):
    return ("geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*lt(X,%s)'"
            % expr)


def clip_y(expr):
    return ("geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='alpha(X,Y)*lt(Y,%s)'"
            % expr)


def tracked_drawtext(path, text, em_px, x0, baseline, colour, track, cap_px):
    """One drawtext per character - drawtext has no letter-spacing option."""
    f = ImageFont.truetype(path, em_px)
    y = baseline - cap_px          # see note on drawtext's y anchor below
    extra = track / 1000.0 * em_px
    out, x = [], float(x0)
    for ch in text:
        t = ch.replace("\\", "\\\\").replace("'", "\\'").replace(",", "\\,")
        if ch != " ":
            out.append("drawtext=fontfile='%s':text='%s':fontcolor=0x%s"
                       ":fontsize=%d:x=%d:y=%d"
                       % (esc(path), t, colour, em_px, int(round(x)), y))
        x += f.getlength(ch) + extra
    return ",".join(out)


def build(outdir=None):
    outdir = outdir or os.path.join(HERE, "renders", "bakeoff_ffmpeg")
    os.makedirs(outdir, exist_ok=True)

    em_name = int(round(S.NAME_CAP / S.NAME_CAP_PER_EM))
    em_charge = int(round(S.CHARGE_CAP / S.CHARGE_CAP_PER_EM))
    # drawtext's `y` is the top of the INK bounding box, NOT the top of the line
    # box. Measured: y = baseline - hhea_ascent put the caps 16px too high
    # (ink rows 764..805 where Blender and PIL both give 780..821). For
    # ALL-CAPS strings the correct anchor is simply y = baseline - cap_height.
    # For mixed case it would be baseline - (tallest ink above baseline), which
    # ffmpeg gives you no way to query - a real limitation, not a preference.
    y_name = S.NAME_BASE - S.NAME_CAP
    tx = S.X0 + S.RULE_W + S.PAD_L

    base = "color=c=black@0.0:s=%dx%d:r=%d" % (S.W, S.H, S.FPS)
    fc = [
        "%s,format=rgba,split=5[b1][b2][b3][b4][b5]" % base,
        "color=c=0x%s@%.3f:s=%dx%d,format=rgba[pl1]"
        % (S.GROUND_HEX, S.PLATE_ALPHA, S.W1, S.T1_H),
        "color=c=0x%s@0.14:s=%dx1,format=rgba[hair]"
        % (S.INK_HEX, S.W1 - S.RULE_W),
        "color=c=0x%s:s=%dx%d,format=rgba[pl2]"
        % (S.RED_HEX, S.W2, S.T2_H),
        "color=c=0x%s:s=%dx%d,format=rgba[rule]"
        % (S.RED_HEX, S.RULE_W, S.T1_H + S.T2_H),
        # tier 1 plate + hairline
        "[b1][pl1]overlay=%d:%d:format=rgb[t1a]" % (S.X0, S.T1_TOP),
        "[t1a][hair]overlay=%d:%d:format=rgb,%s[L1]"
        % (S.X0 + S.RULE_W, S.T1_TOP + S.T1_H - 1, clip_x(E1)),
        # tier 2 plate
        "[b2][pl2]overlay=%d:%d:format=rgb,%s[L2]" % (S.X0, S.T2_TOP, clip_x(E2)),
        # accent rule
        "[b3][rule]overlay=%d:%d:format=rgb,%s[L3]" % (S.X0, S.T1_TOP, clip_y(ER)),
        # name
        "[b4]drawtext=fontfile='%s':text='%s':fontcolor=0x%s:fontsize=%d"
        ":x=%d:y=%d,%s[L4]"
        % (esc(S.NAME_FONT), S.NAME, S.INK_HEX, em_name, tx, y_name,
           clip_x(E1T)),
        # charge, one drawtext per character
        "[b5]%s,%s[L5]"
        % (tracked_drawtext(S.CHARGE_FONT, S.CHARGE, em_charge, tx,
                            S.CHARGE_BASE, S.INK_HEX, S.CHARGE_TRACK, S.CHARGE_CAP),
           clip_x(E2T)),
        "[L1][L2]overlay=format=rgb[o1]",
        "[o1][L3]overlay=format=rgb[o2]",
        "[o2][L4]overlay=format=rgb[o3]",
        "[o3][L5]overlay=format=rgb,format=rgba[out]",
    ]
    cmd = [FFMPEG, "-v", "error", "-y", "-filter_complex", ";".join(fc),
           "-map", "[out]", "-frames:v", str(S.FRAMES), "-start_number", "1",
           os.path.join(outdir, "f_%04d.png")]
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    if p.returncode:
        print(p.stderr[:3000])
        raise SystemExit("ffmpeg failed")
    print("FFMPEG %d frames in %.2fs  (%.4f s/frame)  -> %s"
          % (S.FRAMES, dt, dt / S.FRAMES, outdir))
    print("       filter_complex length: %d chars, %d filter nodes"
          % (len(";".join(fc)), len(";".join(fc).split(","))))
    return dt


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
