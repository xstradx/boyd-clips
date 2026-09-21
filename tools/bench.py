"""The pipeline test bench: known cases with known expected outcomes.

Step 1 of docs/PIPELINE-ARCHITECTURE-AND-LEARNING-LAYER.md §7. This is a
specimen set, not a renderer: it never produces media, it only records which
existing review bundles stand for which situation and what the right outcome
for that situation is, then verifies that the bundles are still the bytes they
were when the bench was written.

    python tools/bench.py build    # (re)write bench/bench.json from the bundles
    python tools/bench.py verify   # every entry still exists, hash unchanged
    python tools/bench.py list     # human-readable table

Adding a case means adding an annotation below and re-running `build`.
Categories come from the situations named in the spec: a boring case, a chaotic
defendant, a money issue, a probation revocation, a lawyer-heavy hearing, and a
case the pipeline should refuse.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "bench" / "bench.json"
REVIEW = ROOT / "out" / "review"

# Annotations are the bench's judgement, so they carry their evidence. An
# outcome nobody recorded stays "unclassified" rather than being invented.
SPECIMENS: list[dict[str, str]] = [
    {
        "dir": "2026-09-10_CqAKrxLobT0_6499",
        "category": "probation revocation",
        "expected": "REFUSE_SHORT",
        "note": ("The editor itself reported 'no valid mini-story' for the allocution stretch; "
                 "the Producer plan forced a Short anyway and the result was rejected by Nathan "
                 "('kind of a lame clip'). The correct Short for this hearing is the plea "
                 "colloquy (seven-year warning, then the record), not the allocution."),
        # Machine-readable counterpart: the shipped Short must not be the
        # refused stretch. The window is the allocution cut that was built and
        # rejected (out/review/2026-09-10_CqAKrxLobT0_6499/superseded_recut_20260916-173335);
        # the editor's own refusal is recorded in logs/2026-09-16.log ("SHORTS_EDITOR_V2
        # found no valid mini-story", 17:33-17:48).
        "checks": [{
            "kind": "short_avoids_window",
            "window_s": [6898.36, 6949.58],
            "why": "the allocution stretch: editor refused it, Nathan rejected the cut",
        }],
    },
    {
        "dir": "2026-09-08_IDGfe1rPUQo_6130",
        "category": "relationship / no-outcome Short",
        "expected": "SHORT_KEEPS_CONVERSATION_STOPS_BEFORE_SENTENCE",
        "note": ("Nathan: more conversation between them, and stop adding the outcome so people "
                 "watch the long-form. Both versions are public; the Short's bytes here are the "
                 "recut that ends before Boyd starts the sentence."),
        # Last kept word vs the sentence's first word: the Short ends on
        # "I understand your" (6549.68) and Boyd's sentence opens on "All right."
        # at 6551.20, both read from the same cached transcript.
        "checks": [{
            "kind": "ends_before_source_word",
            "transcript": "work/IDGfe1rPUQo/IDGfe1rPUQo.transcript.json",
            "sentence": "All right. This is what the court is going to do.",
            "first_word": "All",
            "first_word_s": 6551.2,
        }],
    },
    {
        "dir": "2026-04-30_oL6lV6gCyOc_736",
        "category": "property / exact source hook",
        "expected": "SHORT_OPENS_ON_EXACT_TWO_PART_SOURCE_HOOK",
        "note": ("Approved and posted. The Short opens on the contiguous Boyd line "
                 "('This is the bracelet. I need you to pawn it.') before Perry's quote."),
        # First spoken words vs the approved hook quote.
        "checks": [{
            "kind": "starts_with_source_words",
            "transcript": "work/oL6lV6gCyOc/oL6lV6gCyOc.transcript.json",
            "words": "\"This is the bracelet. I need you to pawn it.",
            "first_word_s": 1338.12,
        }],
    },
    {
        "dir": "2024-03-25_bHAuH5U4NYI_2725",
        "category": "lawyer-heavy hearing",
        "expected": "unclassified",
        "note": ("Recorded from the 2026-09-12 handoff as one of the rehearsal bundles whose "
                 "plan and saved Short were found to diverge; treated as the bench's adversarial "
                 "plan-alignment case. No editorial verdict on record."),
    },
    {
        "dir": "2026-09-08_IDGfe1rPUQo_8988",
        "category": "unclassified",
        "expected": "unclassified",
        "note": "Second case from the same docket as the phone dispute; no editorial verdict on record.",
    },
    {
        "dir": "2026-09-10_CqAKrxLobT0_2364",
        "category": "unclassified",
        "expected": "unclassified",
        "note": ("Second Harrison case from the same docket; carries Sol-era artifact hashes and "
                 "is useful as a cross-model comparison once classified."),
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bundle(dir_name: str) -> dict:
    """Read one review bundle's manifest; never touch the media."""
    manifest_path = REVIEW / dir_name / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"bench: no manifest for {dir_name}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs = data.get("outputs") or {}
    entry: dict = {
        "dir": dir_name,
        "manifest": str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
        "case_key": f"{(data.get('source') or {}).get('video_id')}:"
                    f"{(data.get('case') or {}).get('start_s')}",
        "analysis_model": (data.get("models") or {}).get("analysis_model"),
        "artifacts": {},
    }
    for label in ("longform", "short"):
        record = outputs.get(label) or {}
        path = record.get("file_path")
        if path and Path(path).is_file():
            entry["artifacts"][label] = {
                "path": str(Path(path).relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(Path(path)),
                "duration_s": record.get("duration_s"),
            }
        elif path:
            entry["artifacts"][label] = {"path": str(path), "sha256": None,
                                         "error": "file missing on disk"}
    return entry


def _normalise(text: str) -> str:
    keep = "".join(ch.lower() if (ch.isalnum() or ch.isspace()) else " " for ch in text)
    return " ".join(keep.split())


def _short_plan(data: dict) -> dict:
    return ((data.get("outputs") or {}).get("short") or {}).get("edit_plan") or {}


def _kept_source_times(plan: dict) -> list[float]:
    return [float(w["src_t"]) for w in (plan.get("word_stream") or []) if "src_t" in w]


def _transcript_words(relative_path: str) -> list:
    sys.path.insert(0, str(ROOT / "src"))
    from boydclips.transcribe import Transcript  # noqa: WPS433

    return Transcript.from_json((ROOT / relative_path).read_text(encoding="utf-8")).words


def _phrase_at(words, phrase: str, at_s: float, tolerance_s: float = 2.0) -> bool:
    """Is `phrase` present in the transcript within tolerance of `at_s`?"""
    needle = _normalise(phrase)
    if not needle:
        return False
    wanted = needle.split()
    for i in range(len(words) - len(wanted) + 1):
        if abs(words[i].t - at_s) > tolerance_s:
            continue
        got = _normalise(" ".join(w.w for w in words[i:i + len(wanted)]))
        if got == needle:
            return True
    return False


def _run_check(check: dict, data: dict) -> tuple[bool, str]:
    """(ok, evidence) for one machine-readable expectation."""
    plan = _short_plan(data)
    if not plan:
        return False, "the bundle has no Short edit plan to read"
    kind = check.get("kind")

    if kind == "ends_before_source_word":
        times = _kept_source_times(plan)
        if not times:
            return False, "the Short plan kept no source-timed words"
        boundary = float(check["first_word_s"])
        words = _transcript_words(check["transcript"])
        if not _phrase_at(words, f"{check['first_word']} right.", boundary):
            return False, (f"the transcript does not say {check['first_word']!r} at "
                           f"{boundary:.2f}s — the recorded boundary is wrong")
        last = max(times)
        if last < boundary:
            return True, (f"last kept word {last:.2f}s < sentence start {boundary:.2f}s "
                          f"({check['first_word']!r} at {check['sentence']!r})")
        return False, f"last kept word {last:.2f}s runs into the sentence at {boundary:.2f}s"

    if kind == "starts_with_source_words":
        stream = plan.get("word_stream") or []
        if not stream:
            return False, "the Short plan kept no words"
        record = check["words"]
        opening = " ".join(w["w"] for w in stream[:max(1, len(record.split()))])
        words = _transcript_words(check["transcript"])
        if not _phrase_at(words, record, float(check["first_word_s"])):
            return False, (f"the transcript does not carry the approved hook quote at "
                           f"{check['first_word_s']:.2f}s")
        if _normalise(opening).startswith(_normalise(record)):
            return True, f"opens on {opening!r} at {stream[0]['src_t']:.2f}s (approved hook quote)"
        return False, f"opens on {opening!r}, not the approved quote {record!r}"

    if kind == "short_avoids_window":
        start, end = (float(v) for v in check["window_s"])
        spans = plan.get("segments") or []
        times = _kept_source_times(plan)
        inside = [t for t in times if start <= t <= end]
        overlap = [(a, b) for a, b in spans if min(float(b), end) - max(float(a), start) > 0]
        if inside or overlap:
            return False, (f"the Short uses the refused window {start:.1f}-{end:.1f}s "
                           f"({len(inside)} kept word(s), {len(overlap)} segment(s))")
        return True, (f"the Short stays outside {start:.1f}-{end:.1f}s "
                      f"({check.get('why', 'refused window')})")

    return False, f"unknown check kind {kind!r}"


def build() -> int:
    entries = []
    for specimen in SPECIMENS:
        entry = bundle(specimen["dir"])
        entry.update(category=specimen["category"], expected=specimen["expected"],
                     note=specimen["note"])
        if specimen.get("checks"):
            entry["checks"] = specimen["checks"]
        entries.append(entry)
    payload = {
        "spec": "docs/PIPELINE-ARCHITECTURE-AND-LEARNING-LAYER.md §5",
        "version": 1,
        "cases": entries,
    }
    BENCH.parent.mkdir(parents=True, exist_ok=True)
    BENCH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"bench-build-ok {len(entries)} cases -> {BENCH.relative_to(ROOT)}")
    return 0


def verify() -> int:
    if not BENCH.is_file():
        print("bench: bench/bench.json missing; run `python tools/bench.py build`")
        return 1
    payload = json.loads(BENCH.read_text(encoding="utf-8"))
    problems: list[str] = []
    for entry in payload.get("cases") or []:
        manifest = ROOT / entry["manifest"]
        if not manifest.is_file():
            problems.append(f"{entry['dir']}: manifest missing")
            continue
        for label, record in (entry.get("artifacts") or {}).items():
            path = ROOT / str(record.get("path", ""))
            if not path.is_file():
                problems.append(f"{entry['dir']}: {label} missing")
            elif record.get("sha256") and sha256(path) != record["sha256"]:
                problems.append(f"{entry['dir']}: {label} hash changed")
        if entry.get("expected") == "unclassified":
            print(f"  note: {entry['dir']} has no recorded editorial outcome yet")
    if problems:
        print("bench: FAIL")
        for problem in problems:
            print("  " + problem)
        return 1
    print(f"bench-verify-ok {len(payload.get('cases') or [])} cases, all hashes match")
    return 0


def listing() -> int:
    if not BENCH.is_file():
        print("bench: bench/bench.json missing; run `python tools/bench.py build`")
        return 1
    payload = json.loads(BENCH.read_text(encoding="utf-8"))
    print(f"{'case':<28} {'category':<40} expected")
    for entry in payload.get("cases") or []:
        print(f"{entry['case_key']:<28} {entry['category']:<40} {entry['expected']}")
    return 0


def check() -> int:
    """Compare each specimen's recorded evidence with its expected outcome.

    This is the honest half of a test bench: for every case it reports whether
    the expectation is *supported by machine-readable evidence in the bundle*,
    or whether it can only be settled by watching the video. An expectation
    that nothing can check is listed as such rather than counted as a pass.
    """
    if not BENCH.is_file():
        print("bench: bench/bench.json missing; run `python tools/bench.py build`")
        return 1
    payload = json.loads(BENCH.read_text(encoding="utf-8"))
    supported = unsupported = violated = 0
    for entry in payload.get("cases") or []:
        manifest = ROOT / entry["manifest"]
        data = json.loads(manifest.read_text(encoding="utf-8"))
        editor = data.get("short_editor") or {}
        failed = [g.get("gate") for g in (editor.get("qc") or []) if g.get("critical") and not g.get("ok")]
        refusal = editor.get("refusal") or ""
        expected = entry.get("expected")

        # A recorder expectation calls a human to watch; a machine-readable
        # check gives the same expectation a counterpart that can FAIL. The
        # check is what counts as support — the prose note never does.
        checks = entry.get("checks") or []
        failed_checks: list[str] = []
        evidence: list[str] = []
        for check in checks:
            ok, detail = _run_check(check, data)
            (evidence if ok else failed_checks).append(detail)
        if failed_checks:
            verdict = "VIOLATED: " + "; ".join(failed_checks)
            violated += 1
        elif checks:
            verdict = "supported: " + "; ".join(evidence)
            supported += 1
        elif expected == "REFUSE_SHORT":
            if refusal or failed:
                verdict = f"supported: editor recorded a refusal ({refusal or ', '.join(failed)})"
                supported += 1
            else:
                verdict = ("not machine-checkable here: this bundle now carries an accepted Short; "
                           "the refusal belongs to the allocution plan (see note)")
                unsupported += 1
        elif expected and expected != "unclassified":
            verdict = ("not machine-checkable: the rule is editorial (what the Short keeps or drops) — "
                       "needs a watch, not a hash")
            unsupported += 1
        else:
            verdict = "no expectation recorded"
            unsupported += 1
        print(f"{entry['case_key']:<24} {expected:<46} {verdict}")
    print(f"bench-check: {supported} supported by recorded evidence, "
          f"{unsupported} needing editorial review, {violated} violated "
          "(no rule counted as a pass it cannot prove)")
    # 2026-09-16: this used to exit 0 either way, which made "the bench cannot
    # prove anything yet" a status line nobody had to act on. It is now a
    # failing gate: a specimen whose expectation has no machine-readable
    # counterpart is an unmet gate, not a note. `--allow-unproven` reports the
    # same table without failing, for planning sessions.
    if payload.get("_allow_unproven") is True:
        return 0
    return 0 if unsupported == 0 and violated == 0 else 1


if __name__ == "__main__":
    argv = sys.argv[1:]
    command = argv[0] if argv else "list"
    if "--allow-unproven" in argv and BENCH.is_file():
        payload = json.loads(BENCH.read_text(encoding="utf-8"))
        payload["_allow_unproven"] = True
        BENCH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            raise SystemExit(check())
        finally:
            payload.pop("_allow_unproven", None)
            BENCH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    raise SystemExit({"build": build, "verify": verify, "list": listing,
                      "check": check}.get(command, listing)())
