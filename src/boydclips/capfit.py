"""Story-preserving long-form duration cap (2026-09-06).

`produce()` used to enforce `output.longform.max_duration_s` by walking the
dead-air-trimmed pieces in order and dropping everything after the budget ran
out — the TAIL. A case that scored MAKE on a payoff near its end (Jimenez:
1,387 s, ruling at the end) was selected for exactly the material the render
then cut.

This module replaces that with a plan that protects the story first and spends
what is left on the material closest to it:

  1. PROTECTED regions (must survive in full, or the fit fails explicitly):
       setup     the first `setup_s` of the case — the call, who, why
       payoff    `money_moment_s - payoff_lead_s` .. `+ payoff_aftermath_s`
       ending    the last `ending_s` of the case — the ruling / consequence
     plus the model's own short beats (`short_segments`) when present. These
     are the pipeline's existing structured timestamps; no new model call.
  2. The remaining budget is filled with the rest of the pieces in order of
     distance to the nearest protected anchor (closest first), so the
     escalation around the payoff survives and far-away procedural stretches
     are what get dropped. The marginal chunk is trimmed at its far edge so
     what is kept stays contiguous with its anchor.
  3. If the protected regions alone exceed the cap, `CapFitError` is raised
     with the numbers. Nothing is silently cut. The caller treats it as a
     production failure (the case is skipped with the reason logged, the docket
     stays pending) — the last fallback the ruleset allows.

Everything is in SOURCE seconds, chronological, and the result never exceeds
the cap. A case that already fits is returned untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .render import Segment

DEFAULTS: dict[str, float] = {
    "setup_s": 90.0,            # docket call + who/why
    "payoff_lead_s": 30.0,      # the question / claim that the payoff answers
    "payoff_aftermath_s": 60.0, # the reaction and what follows
    "ending_s": 45.0,           # the ruling / consequence at the end of the case
    "min_piece_s": 2.0,         # never keep a sliver shorter than this
}


class CapFitError(RuntimeError):
    """The protected story does not fit the cap. Explicit, never silent."""


@dataclass
class CapFitPlan:
    pieces: list[Segment]
    dropped: list[tuple[float, float]]
    protected: list[tuple[float, float]]
    anchors: list[tuple[float, float]]
    money_moment_s: float | None
    money_moment_source: str
    before_s: float
    after_s: float
    cap_s: float
    changed: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        r = lambda x: round(float(x), 2)
        return {
            "changed": self.changed,
            "cap_s": self.cap_s,
            "before_s": r(self.before_s),
            "after_s": r(self.after_s),
            "money_moment_s": None if self.money_moment_s is None else r(self.money_moment_s),
            "money_moment_source": self.money_moment_source,
            "protected": [(r(a), r(b)) for a, b in self.protected],
            "anchors": [(r(a), r(b)) for a, b in self.anchors],
            "kept": [(r(p.start_s), r(p.end_s)) for p in self.pieces],
            "dropped": [(r(a), r(b)) for a, b in self.dropped],
            "notes": list(self.notes),
        }


# ------------------------------------------------------------------ helpers
def _merge(intervals: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted((min(a, b), max(a, b)) for a, b in intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out if b > a]


def _clip(intervals, lo, hi):
    return [(max(a, lo), min(b, hi)) for a, b in intervals if min(b, hi) > max(a, lo)]


def _overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def resolve_money_moment(case: dict[str, Any], lo: float, hi: float) -> tuple[float | None, str]:
    """The payoff timestamp, from the structured outputs already on the case.

    Order: editorial.money_moment_s (BOYD_EDITORIAL_V2) -> the short plan's
    turn/button beat -> hook_start_s -> None (only setup + ending are protected).
    A value outside the case span is ignored, with the source saying so.
    """
    ed = case.get("editorial") or {}
    cands: list[tuple[float | None, str]] = [(ed.get("money_moment_s"), "editorial.money_moment_s")]
    segs = case.get("short_segments") or []
    for beat in ("turn", "button", "moment"):
        for s in segs:
            if s.get("beat") == beat:
                cands.append((s.get("start_s"), f"short_segments.{beat}"))
                break
    cands.append((case.get("hook_start_s"), "hook_start_s"))
    ignored: list[str] = []
    for v, src in cands:
        if v is None:
            continue
        try:
            t = float(v)
        except (TypeError, ValueError):
            continue
        if lo <= t <= hi:
            return t, src
        ignored.append(f"{src}={t:g} outside case {lo:g}-{hi:g}")
    return None, "none (setup + ending only" + (f"; ignored {', '.join(ignored)}" if ignored else "") + ")"


def protected_regions(case: dict[str, Any], lo: float, hi: float, cfg: dict[str, float]
                      ) -> tuple[list[tuple[float, float]], list[tuple[float, float]], float | None, str]:
    """(protected, anchors, money_moment_s, source). Protected must survive whole;
    anchors additionally pull the fill toward them."""
    mm, src = resolve_money_moment(case, lo, hi)
    prot: list[tuple[float, float]] = [(lo, lo + cfg["setup_s"]), (hi - cfg["ending_s"], hi)]
    if mm is not None:
        prot.append((mm - cfg["payoff_lead_s"], mm + cfg["payoff_aftermath_s"]))
    anchors = list(prot)
    for s in case.get("short_segments") or []:
        try:
            a, b = float(s["start_s"]), float(s["end_s"])
        except (KeyError, TypeError, ValueError):
            continue
        if b > a:
            anchors.append((a, b))
    return _merge(_clip(prot, lo, hi)), _merge(_clip(anchors, lo, hi)), mm, src


def _distance_to_anchors(a: float, b: float, anchors) -> float:
    best = float("inf")
    for x0, x1 in anchors:
        if _overlap(a, b, x0, x1) > 0:
            return 0.0
        best = min(best, x0 - b if x0 >= b else a - x1)
    return best


# ------------------------------------------------------------------ the plan
def _subtract(free, dropped):
    out = []
    for f0, f1 in free:
        cursor = f0
        for d0, d1 in dropped:
            if d1 <= f0 or d0 >= f1:
                continue
            if d0 > cursor:
                out.append((cursor, d0))
            cursor = max(cursor, d1)
        if cursor < f1:
            out.append((cursor, f1))
    return _merge(out)


def _free_floor(t, protected, free):
    """Lowest time an edge at t may move down to without leaving its free run."""
    for f0, f1 in free:
        if f0 - 1e-9 <= t <= f1 + 1e-9:
            return f0
    return t


def _free_ceiling(t, protected, free):
    for f0, f1 in free:
        if f0 - 1e-9 <= t <= f1 + 1e-9:
            return f1
    return t


def _nearest_gap_edge(t, gaps, snap_s, want, limit_lo=None, limit_hi=None):
    """The nearest word-gap edge to t within snap_s, moving OUTWARD only:
    want='end'   -> a gap's END at or below t (the cut starts after the last word)
    want='start' -> a gap's START at or above t (the cut ends before the next word)."""
    best, best_d = None, snap_s + 1e-9
    for g0, g1 in gaps:
        if want == "end":
            cand = g1 if g1 <= t else (g0 if g0 <= t else None)
            if cand is None or (limit_lo is not None and cand < limit_lo):
                continue
            d = t - cand
        else:
            cand = g0 if g0 >= t else (g1 if g1 >= t else None)
            if cand is None or (limit_hi is not None and cand > limit_hi):
                continue
            d = cand - t
        if 0 <= d < best_d:
            best, best_d = cand, d
    return best


def word_gaps(words, lo: float, hi: float, min_gap_s: float = 0.5) -> list[tuple[float, float]]:
    """(start, end) of every pause >= min_gap_s between consecutive transcript
    words inside [lo, hi]. `words` are objects/dicts with a time `t`."""
    ts = sorted(float(w["t"] if isinstance(w, dict) else w.t) for w in words)
    ts = [t for t in ts if lo <= t <= hi]
    return [(a, b) for a, b in zip(ts, ts[1:]) if b - a >= min_gap_s]


def plan_cap_fit(pieces: Sequence[Segment], cap_s: float, case: dict[str, Any],
                 cfg: dict[str, Any] | None = None,
                 gaps: Sequence[tuple[float, float]] | None = None, snap_s: float = 3.0) -> CapFitPlan:
    """Fit chronological `pieces` (source seconds) into `cap_s` without losing
    the story. See the module docstring for the rules. `gaps` (word pauses from
    the transcript) lets interior cuts snap to a pause within `snap_s`."""
    c = dict(DEFAULTS)
    c.update({k: float(v) for k, v in (cfg or {}).items() if k in DEFAULTS})
    pieces = sorted(pieces, key=lambda p: p.start_s)
    before = sum(p.duration for p in pieces)
    lo = min(p.start_s for p in pieces) if pieces else float(case.get("start_s", 0.0))
    hi = max(p.end_s for p in pieces) if pieces else float(case.get("end_s", 0.0))
    protected, anchors, mm, mm_src = protected_regions(case, lo, hi, c)

    if before <= cap_s + 1e-9:
        return CapFitPlan(list(pieces), [], protected, anchors, mm, mm_src, before, before, cap_s, False,
                          [f"{before:.0f}s fits the {cap_s:.0f}s cap; unchanged"])

    # 1. what the protected regions cost, measured on the pieces (dead air
    #    inside a protected region is already gone, so this is real runtime)
    required = 0.0
    for p in pieces:
        for a, b in protected:
            required += _overlap(p.start_s, p.end_s, a, b)
    if required > cap_s + 1e-9:
        raise CapFitError(
            f"protected story ({required:.0f}s: setup {c['setup_s']:.0f}s + payoff window "
            f"{c['payoff_lead_s']:.0f}+{c['payoff_aftermath_s']:.0f}s around {mm_src} + ending "
            f"{c['ending_s']:.0f}s) exceeds the {cap_s:.0f}s cap; the case cannot be cut to the "
            f"cap without losing its payoff — refusing rather than truncating"
        )

    # 2. carve every piece into protected and free chunks
    Chunk = tuple[float, float, bool]   # (start, end, protected)
    chunks: list[Chunk] = []
    for p in pieces:
        cuts = sorted({p.start_s, p.end_s} | {x for a, b in protected for x in (a, b) if p.start_s < x < p.end_s})
        for a, b in zip(cuts, cuts[1:]):
            mid = (a + b) / 2
            chunks.append((a, b, any(x0 <= mid <= x1 for x0, x1 in protected)))

    # 3. fill the remaining budget by DISTANCE TO THE STORY: every anchor
    #    (protected regions + the model's short beats) grows outward by the
    #    same radius r, and r is the largest value whose kept free time fits
    #    the budget. What is dropped is therefore the free material farthest
    #    from any anchor — the middle of a long testimony, a procedural
    #    stretch — never the run-up to the payoff or the beats themselves.
    #    Contiguous by construction, so no confetti of slivers.
    budget = cap_s - required
    free = _merge([(a, b) for a, b, prot in chunks if not prot])

    def kept_at(r: float) -> list[tuple[float, float]]:
        grown = _merge([(x0 - r, x1 + r) for x0, x1 in anchors])
        out: list[tuple[float, float]] = []
        for f0, f1 in free:
            for g0, g1 in grown:
                o0, o1 = max(f0, g0), min(f1, g1)
                if o1 > o0:
                    out.append((o0, o1))
        return _merge(out)

    def measure(iv) -> float:
        return sum(b - a for a, b in iv)

    free_total = measure(free)
    if free_total <= budget + 1e-9:
        kept_free = list(free)
    else:
        lo_r, hi_r = 0.0, max(hi - lo, 1.0)
        for _ in range(60):                      # ~1e-15 relative precision; deterministic
            mid = (lo_r + hi_r) / 2
            if measure(kept_at(mid)) <= budget:
                lo_r = mid
            else:
                hi_r = mid
        kept_free = kept_at(lo_r)                # largest radius that still fits
    dropped: list[tuple[float, float]] = []
    for f0, f1 in free:
        cursor = f0
        for k0, k1 in kept_free:
            if k1 <= f0 or k0 >= f1:
                continue
            if k0 > cursor:
                dropped.append((cursor, k0))
            cursor = max(cursor, k1)
        if cursor < f1:
            dropped.append((cursor, f1))

    # 3b. snap each interior cut to a pause so the jump lands between words,
    #     not inside one. Edges move OUTWARD only (more dropped, never more
    #     kept, so the cap still holds) and never into a protected region.
    if gaps and dropped:
        snapped: list[tuple[float, float]] = []
        for d0, d1 in dropped:
            n0 = _nearest_gap_edge(d0, gaps, snap_s, want="end", limit_lo=_free_floor(d0, protected, free))
            n1 = _nearest_gap_edge(d1, gaps, snap_s, want="start", limit_hi=_free_ceiling(d1, protected, free))
            snapped.append((n0 if n0 is not None else d0, n1 if n1 is not None else d1))
        dropped = _merge(snapped)
        kept_free = _subtract(free, dropped)

    keep_all = _merge([(a, b) for a, b, prot in chunks if prot] + kept_free)
    # re-express as pieces: intersect the kept set with the original pieces so
    # no piece boundary (a dead-air cut) is ever bridged
    out: list[Segment] = []
    for p in pieces:
        for a, b in keep_all:
            o0, o1 = max(a, p.start_s), min(b, p.end_s)
            if o1 - o0 >= c["min_piece_s"] or any(_overlap(o0, o1, x0, x1) > 0 for x0, x1 in protected):
                if o1 > o0:
                    out.append(Segment(o0, o1))
    out.sort(key=lambda s: s.start_s)
    after = sum(p.duration for p in out)

    # 4. invariants — a violated one is a bug, not a warning
    if after > cap_s + 1e-6:
        raise CapFitError(f"internal: planned {after:.1f}s exceeds cap {cap_s:.0f}s")
    for a, b in protected:
        want = sum(_overlap(p.start_s, p.end_s, a, b) for p in pieces)
        got = sum(_overlap(p.start_s, p.end_s, a, b) for p in out)
        if got + 1e-6 < want:
            raise CapFitError(f"internal: protected region {a:.0f}-{b:.0f} lost {want - got:.1f}s")

    notes = [
        f"{before:.0f}s -> {after:.0f}s to fit the {cap_s:.0f}s cap",
        f"protected {required:.0f}s (setup/payoff/ending via {mm_src}); "
        f"dropped {sum(b - a for a, b in dropped):.0f}s of lower-value material",
    ]
    return CapFitPlan(out, _merge(dropped), protected, anchors, mm, mm_src, before, after, cap_s, True, notes)


def describe(plan: CapFitPlan) -> str:
    fmt = lambda t: f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    lines = [f"cap-fit: {'CHANGED' if plan.changed else 'unchanged'}  {plan.before_s:.0f}s -> {plan.after_s:.0f}s  (cap {plan.cap_s:.0f}s)",
             f"  money moment: {'none' if plan.money_moment_s is None else fmt(plan.money_moment_s)} via {plan.money_moment_source}",
             "  protected: " + ", ".join(f"{fmt(a)}–{fmt(b)}" for a, b in plan.protected)]
    if plan.dropped:
        lines.append("  dropped:   " + ", ".join(f"{fmt(a)}–{fmt(b)} ({b - a:.0f}s)" for a, b in plan.dropped))
    lines.append("  kept:      " + ", ".join(f"{fmt(p.start_s)}–{fmt(p.end_s)}" for p in plan.pieces))
    return "\n".join(lines)
