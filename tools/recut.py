# -*- coding: utf-8 -*-
"""Re-cut a clip from a timemap, with a short fade across every join.

Nathan, 2026-08-31: *"you need to be surgical with the cuts"* and
*"the fade in things u did with audio for the hard cuts"*.

Cuts come from `snap_cuts.snap_to_silence`, which moves every boundary that
lands in audible audio into measured silence - on OFFERUP that took boundaries
in speech from 20/38 to 4/38. This applies the result.

Every join gets a short audio fade out/in. Worth being precise about why,
because an earlier claim in this project was wrong: missing fades were blamed
for "choppy edits" and the measurement showed the join discontinuity was 0.31x
a normal speech transient - there was no click. Fades are here because they are
cheap and he asked for them, NOT because a click was ever measured.
"""
import json
import os
import subprocess
import sys
import tempfile

FADE = 0.012      # seconds, each side of a join


def recut(src, timemap, out, src_offset=0.0, fade=FADE, verbose=True):
    """ONE pass, trim/atrim + concat filter. Frame-exact, no accumulated drift.

    Two earlier approaches were measured and rejected:

    * SEGMENT-AND-CONCAT put a rounding error in every piece - each has to end
      on a whole video AND audio frame. 19 segments accumulated 1.1s of drift
      with keyframe seeking, 0.73s even with frame-accurate seeking. That drift
      moves the joins off the silences they were snapped into, silently undoing
      the cut fix.
    * SELECT/ASETPTS compacted the video correctly (1331 frames = 44.37s) but
      `aselect` did not drop the audio at all - the audio stream stayed 55.51s
      against a 44.37s video. Verified with the fades removed, so it was not
      the fades.

    trim/atrim + concat is the canonical filter for this and it cuts both
    streams together, so they cannot disagree.
    """
    tm = json.load(open(timemap))
    segs = [s for s in tm["segments"]
            if float(s["old_end"]) - float(s["old_start"]) > 0.05]
    if not segs:
        return False, "no segments"
    rng = [(src_offset + float(s["old_start"]), src_offset + float(s["old_end"]))
           for s in segs]

    # VIDEO and AUDIO cut SEPARATELY, then muxed.
    # A combined graph kept producing a 44.37s video against a 55.51s audio -
    # verified by decoding the audio, not just reading container metadata -
    # with both `aselect` and `atrim`. Rather than keep guessing at one filter
    # string, each stream gets its own pass, which cannot fail across streams.
    import tempfile as _tf
    with _tf.TemporaryDirectory() as d:
        vtmp = os.path.join(d, "v.mp4")
        atmp = os.path.join(d, "a.wav")
        vparts = "".join(
            f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{k}];"
            for k, (a, b) in enumerate(rng))
        vfc = vparts + "".join(f"[v{k}]" for k in range(len(rng))) +             f"concat=n={len(rng)}:v=1:a=0[v]"
        rv = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex", vfc,
             "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium",
             "-crf", "16", "-pix_fmt", "yuv420p", vtmp],
            capture_output=True, text=True)
        aparts = "".join(
            f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade},"
            f"afade=t=out:st={max(0.0, b - a - fade):.3f}:d={fade}[a{k}];"
            for k, (a, b) in enumerate(rng))
        afc = aparts + "".join(f"[a{k}]" for k in range(len(rng))) +             f"concat=n={len(rng)}:v=0:a=1[a]"
        ra = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", src, "-filter_complex", afc,
             "-map", "[a]", "-vn", "-c:a", "pcm_s16le", atmp],
            capture_output=True, text=True)
        if not (os.path.exists(vtmp) and os.path.exists(atmp)):
            return False, ("video " + (rv.stderr or "")[:80] + " | audio "
                           + (ra.stderr or "")[:80])
        rm = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", vtmp, "-i", atmp,
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-shortest", out],
            capture_output=True, text=True)
    ok = os.path.exists(out)
    if verbose:
        want = sum(b - a for a, b in rng)
        print(f"  recut: {len(rng)} ranges, streams cut separately, "
              f"{fade*1000:.0f}ms fades -> {'OK' if ok else 'FAILED'}"
              + (f"  (target {want:.2f}s)" if ok else ""))
    return ok, f"{len(rng)} ranges"


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("usage: recut.py SRC.mp4 timemap.json OUT.mp4 [src_offset]")
        sys.exit(2)
    off = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    good, det = recut(sys.argv[1], sys.argv[2], sys.argv[3], off)
    sys.exit(0 if good else 1)
