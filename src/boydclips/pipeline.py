"""The daily run.

    discover -> transcribe -> segment -> gate+score -> select
             -> render (long-form, then short) -> package -> publish -> ledger

Every stage is idempotent and checkpointed in the state DB, so a crashed run
can simply be re-invoked. Nothing here decides policy — thresholds, formats,
and safety rules live in config/ and spec/.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import traceback
from datetime import date
from pathlib import Path
from typing import Any

from . import discover, render
from .analyze import Analyzer, RefusalError
from .config import SPEC_VERSION, Config, load_config
from .publish import publish_pair
from .state import Store
from .transcribe import get_transcript, hhmmss

log = logging.getLogger("boydclips")


def setup_logging(cfg: Config, verbose: bool = False) -> None:
    log_dir = cfg.path("paths.logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / f"{date.today().isoformat()}.log", encoding="utf-8"),
        ],
    )


class Pipeline:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load_config()
        self.store = Store(self.cfg.path("paths.state_db"))
        self.work = self.cfg.path("paths.work")
        self.out = self.cfg.path("paths.out")
        self._analyzer: Analyzer | None = None

    @property
    def analyzer(self) -> Analyzer:
        # Deferred so `discover`/`stats` work without an API key present.
        if self._analyzer is None:
            self._analyzer = Analyzer(self.cfg)
        return self._analyzer

    def close(self) -> None:
        self.store.close()

    # ------------------------------------------------------------------ stages

    def discover(self) -> list[discover.Docket]:
        found = discover.list_recent(
            self.cfg.require("source.channel_url"),
            self.cfg.get("source.scan_depth", 8),
        )
        seen = {d.video_id for d in found if self.store.seen_docket(d.video_id)}
        new = discover.filter_new(
            found,
            seen=seen,
            min_duration_s=self.cfg.get("source.min_duration_s", 900),
            max_age_days=self.cfg.get("source.max_age_days", 4),
        )
        for d in new:
            self.store.add_docket(d.video_id, d.title, d.docket_date, d.duration_s)
        log.info("discover: %d streams listed, %d new and eligible", len(found), len(new))
        return new

    def analyze_docket(self, docket: discover.Docket) -> list[dict[str, Any]]:
        work = self.work / docket.video_id
        work.mkdir(parents=True, exist_ok=True)

        cached = work / "scored.json"
        if cached.exists():
            log.info("  analysis: reusing cached result")
            return json.loads(cached.read_text(encoding="utf-8"))

        log.info("  transcript: fetching")
        transcript = get_transcript(
            docket.video_id,
            work,
            source=self.cfg.get("transcription.source", "auto_captions"),
            language=self.cfg.get("transcription.language", "en"),
            whisper_fallback=self.cfg.get("transcription.whisper_fallback", True),
            whisper_model=self.cfg.get("transcription.whisper_model", "medium"),
        )
        log.info(
            "  transcript: %d words, %s, via %s",
            len(transcript.words), hhmmss(transcript.duration_s), transcript.source,
        )
        self.store.mark_docket(docket.video_id, "transcribed", transcribed_at=_now())

        meta = {"title": docket.title, "docket_date": docket.docket_date, "url": docket.url}

        log.info("  segment: splitting docket into cases")
        cases = self.analyzer.segment(transcript, meta)
        log.info("  segment: %d substantive cases found", len(cases))
        if not cases:
            return []

        log.info("  score: applying safety gate and rubric")
        scored = self.analyzer.score(transcript, cases, meta)

        passed = [c for c in scored if c["eligible"]]
        rejected = [c for c in scored if not c["eligible"]]
        safety_blocked = [c for c in rejected if not c["safety"]["safety_pass"]]
        log.info(
            "  score: %d eligible, %d rejected (%d on safety)",
            len(passed), len(rejected), len(safety_blocked),
        )
        for c in safety_blocked:
            log.info(
                "    safety reject @%s: %s",
                hhmmss(c["start_s"]),
                ", ".join(c["safety"]["safety_rule_violations"]) or "unspecified",
            )

        cached.write_text(json.dumps(scored, ensure_ascii=False, indent=2), encoding="utf-8")
        self.store.mark_docket(docket.video_id, "analyzed", analyzed_at=_now())
        for case in scored:
            self.store.save_case(docket.video_id, case, case.get("rank"))
        return scored

    def produce(self, docket: discover.Docket, case: dict[str, Any]) -> dict[str, Any]:
        """Download, cut, caption, and package one selected case."""
        work = self.work / docket.video_id
        case_key = self.store.case_key(docket.video_id, case["start_s"])
        stamp = f"{docket.docket_date or 'undated'}_{docket.video_id}"
        review_dir = self.out / "review" / stamp
        review_dir.mkdir(parents=True, exist_ok=True)

        transcript = get_transcript(docket.video_id, work)
        meta = {"title": docket.title, "docket_date": docket.docket_date, "url": docket.url}

        log.info("  package: writing titles and description")
        pkg = self.analyzer.package(transcript, case, meta, SPEC_VERSION)
        if not pkg["hook_verified"]:
            log.warning(
                "  package: hook line not found verbatim in transcript — "
                "CONTENT_SPEC §6 requires titles the clip proves. Flagging for review."
            )

        lf_cfg = self.cfg.require("output.longform")
        sh_cfg = self.cfg.require("output.short")

        lf_start = max(0.0, case["start_s"] - lf_cfg.get("pad_before_s", 4.0))
        lf_end = case["end_s"] + lf_cfg.get("pad_after_s", 3.0)

        log.info(
            "  download: section %s–%s (%.1f min, not the full %.1f hr stream)",
            hhmmss(lf_start), hhmmss(lf_end),
            (lf_end - lf_start) / 60, docket.duration_s / 3600,
        )
        source, offset = render.download_section(
            docket.video_id, lf_start, lf_end, work / f"{case_key.replace(':', '_')}.mp4"
        )

        crop = None
        if sh_cfg.get("autocrop", True):
            crop = render.detect_content_crop(source)
            log.info("  framing: %s", f"letterbox stripped -> {crop}" if crop
                     else "no baked-in letterbox detected")

        log.info("  render: long-form")
        lf_path = review_dir / "longform.mp4"
        lf_duration = render.render_longform(
            source, offset, [render.Segment(lf_start, lf_end)], lf_cfg, lf_path, crop=crop
        )
        lf_clip_id = self.store.save_clip(
            case_key, "longform", lf_path, lf_duration,
            pkg["longform_title"], "", SPEC_VERSION,
        )

        lf_description = self.cfg.require("packaging.longform.description_template").format(
            summary=pkg["summary"],
            proceeding_type=case["proceeding_type"].replace("_", " ").title(),
            court=self.cfg.require("source.court"),
            docket_date=docket.docket_date or "unknown",
            source_url=docket.url,
            start_timestamp=hhmmss(case["start_s"]),
        )
        self.store.set_clip_description(lf_clip_id, lf_description)

        result: dict[str, Any] = {
            "case_key": case_key,
            "review_dir": review_dir,
            "package": pkg,
            "longform": {
                "clip_id": lf_clip_id,
                "file_path": str(lf_path),
                "title": pkg["longform_title"],
                "description": lf_description,
                "duration_s": lf_duration,
            },
            "short": None,
        }

        segments = render.plan_short_segments(case, sh_cfg)
        if not case.get("shortable") or segments is None:
            log.info(
                "  render: no short — %s",
                case.get("shortable_reasoning") or "beat plan failed validation",
            )
            self._write_manifest(review_dir, docket, case, pkg, result)
            return result

        log.info("  render: short (%d beats, %.1fs)", len(segments),
                 sum(s.duration for s in segments))

        mode, caption_margin = render.choose_vertical_layout(source, crop, sh_cfg)
        log.info("  framing: vertical mode=%s, caption margin=%dpx", mode, caption_margin)

        ass_path = None
        cap_cfg = dict(sh_cfg.get("captions", {}))
        cap_cfg["margin_v"] = caption_margin
        if cap_cfg.get("enabled", True):
            words: list[Any] = []
            elapsed = 0.0
            for seg in segments:
                for w in transcript.slice(seg.start_s, seg.end_s):
                    shifted = type(w)(t=elapsed + (w.t - seg.start_s), w=w.w)
                    words.append(shifted)
                elapsed += seg.duration
            ass_path = render.build_ass(
                words, 0.0, elapsed, cap_cfg,
                self.cfg.get("packaging.short.end_card"),
                review_dir / "captions.ass",
            )

        sh_path = review_dir / "short.mp4"
        sh_duration = render.render_short(
            source, offset, segments, sh_cfg, ass_path, sh_path, crop=crop
        )
        sh_clip_id = self.store.save_clip(
            case_key, "short", sh_path, sh_duration, pkg["short_title"], "", SPEC_VERSION
        )
        result["short"] = {
            "clip_id": sh_clip_id,
            "file_path": str(sh_path),
            "title": pkg["short_title"],
            "description": "",  # filled after the long-form URL exists
            "duration_s": sh_duration,
        }

        try:
            render.extract_thumbnail(
                source, max(0.0, case["hook_start_s"] - offset), review_dir / "thumbnail.jpg"
            )
        except Exception as exc:  # a missing thumbnail must not fail the run
            log.debug("  thumbnail extraction skipped: %s", exc)

        self._write_manifest(review_dir, docket, case, pkg, result)
        return result

    # ------------------------------------------------------------------ driver

    def run_daily(self, limit: int | None = None, dry_run: bool = False) -> list[dict[str, Any]]:
        new = self.discover()
        if not new:
            log.info("nothing new to process")
            return []

        per_day = limit or self.cfg.get("output.clips_per_day", 1)
        produced: list[dict[str, Any]] = []

        for docket in new:
            log.info("docket %s — %s", docket.video_id, docket.title)
            try:
                scored = self.analyze_docket(docket)
            except RefusalError as exc:
                log.error("  %s — skipping docket", exc)
                self.store.mark_docket(docket.video_id, "refused", str(exc))
                continue
            except Exception as exc:
                log.error("  analysis failed: %s", exc)
                log.debug(traceback.format_exc())
                self.store.mark_docket(docket.video_id, "error", str(exc))
                continue

            eligible = [c for c in scored if c["eligible"]]
            if not eligible:
                log.info("  no case cleared the gates — nothing to publish today")
                self.store.mark_docket(docket.video_id, "no_eligible_cases")
                continue

            picks = eligible[: max(1, per_day)]
            bank = eligible[len(picks):] if self.cfg.get("output.bank_extras") else []
            if bank:
                log.info("  banking %d runner-up case(s) for slow days", len(bank))

            for case in picks:
                key = self.store.case_key(docket.video_id, case["start_s"])
                if self.store.case_published(key):
                    log.info("  case %s already published — skipping", key)
                    continue
                if dry_run:
                    log.info(
                        "  [dry-run] would produce: %s (score %.1f) — %s",
                        key, case["total_score"], case["summary"][:90],
                    )
                    continue

                try:
                    result = self.produce(docket, case)
                except Exception as exc:
                    log.error("  production failed: %s", exc)
                    log.debug(traceback.format_exc())
                    continue

                report = publish_pair(
                    self.cfg, self.store,
                    longform=result["longform"],
                    short=result["short"],
                    context={"hook_line": result["package"]["hook_line"]},
                )
                result["publish"] = report
                for note in report.get("skipped", []):
                    log.info("  publish: %s", note)
                for platform, info in report.get("short", {}).items():
                    if "url" in info:
                        log.info("  published short to %s: %s", platform, info["url"])
                    else:
                        log.warning("  %s: %s", platform, info.get("error"))
                if report.get("longform", {}).get("url"):
                    log.info("  published long-form: %s", report["longform"]["url"])

                produced.append(result)
                log.info("  done -> %s", result["review_dir"])

            self.store.mark_docket(docket.video_id, "complete")

        return produced

    # ------------------------------------------------------------------ output

    def _write_manifest(
        self,
        review_dir: Path,
        docket: discover.Docket,
        case: dict[str, Any],
        pkg: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """SAFETY_RULES R10: every clip must be reconstructible from its record."""
        manifest = {
            "spec_version": SPEC_VERSION,
            "generated_at": _now(),
            "source": {
                "video_id": docket.video_id,
                "url": docket.url,
                "title": docket.title,
                "docket_date": docket.docket_date,
                "session": docket.session,
            },
            "case": {
                "start_s": case["start_s"],
                "end_s": case["end_s"],
                "start_timestamp": hhmmss(case["start_s"]),
                "end_timestamp": hhmmss(case["end_s"]),
                "defendant_name": case.get("defendant_name"),
                "cause_number": case.get("cause_number"),
                "proceeding_type": case.get("proceeding_type"),
                "guilt_posture": case.get("guilt_posture"),
            },
            "safety": case["safety"],
            "scores": case["scores"],
            "total_score": case["total_score"],
            "shortable": case.get("shortable"),
            "shortable_reasoning": case.get("shortable_reasoning"),
            "packaging": pkg,
            "models": {
                "analysis_model": self.cfg.require("analysis.model"),
                "effort": self.cfg.get("analysis.effort"),
                "prompt_versions": dict(self.analyzer.prompt_versions),
            },
            "outputs": {
                k: {kk: vv for kk, vv in v.items() if kk != "description"}
                for k, v in result.items()
                if k in ("longform", "short") and v
            },
        }
        (review_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        lf = result["longform"]
        sh = result["short"]
        lines = [
            f"REVIEW — {docket.docket_date or 'undated'}  ({docket.video_id})",
            "=" * 72,
            "",
            f"Case at {hhmmss(case['start_s'])} in the source stream",
            f"Score: {case['total_score']:.1f}   Posture: {case.get('guilt_posture')}",
            f"Safety: PASS  ({case['safety']['safety_reasoning'][:200]})",
            "",
            "LONG-FORM",
            f"  file:  longform.mp4  ({lf['duration_s']:.0f}s)",
            f"  title: {lf['title']}",
            "",
        ]
        if sh:
            lines += [
                "SHORT",
                f"  file:  short.mp4  ({sh['duration_s']:.0f}s)",
                f"  title: {sh['title']}",
                f"  hook:  {pkg['hook_line']}",
                f"  hook verified against transcript: {pkg['hook_verified']}",
                "",
            ]
        else:
            lines += ["SHORT", "  none — case was not shortable", ""]
        lines += [
            "DESCRIPTION (long-form)",
            "-" * 72,
            lf["description"],
            "",
            "-" * 72,
            "Approve:  boyd approve " + result["case_key"],
            "Reject:   boyd reject " + result["case_key"] + ' --reason "..."',
        ]
        (review_dir / "REVIEW.txt").write_text("\n".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------ upkeep

    def cleanup(self) -> None:
        keep_days = self.cfg.get("retention.work_days", 3)
        cutoff = time.time() - keep_days * 86400
        removed = 0
        if self.work.exists():
            for child in self.work.iterdir():
                if not child.is_dir() or child.stat().st_mtime >= cutoff:
                    continue
                # Transcripts are tiny and make re-scoring free — keep them.
                for f in child.iterdir():
                    if f.is_file() and not f.name.endswith(".transcript.json"):
                        f.unlink(missing_ok=True)
                        removed += 1
                    elif f.is_dir():
                        shutil.rmtree(f, ignore_errors=True)
        log.info("cleanup: removed %d stale work file(s)", removed)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
