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
import subprocess
import shutil
import time
import traceback
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from . import analyze, capfit, competitor, cta, diarize, discover, judges, metadata, momentrun, producer_brain, readiness, render, stage_context, thumbnail, short_thumbnail, narrated_short_intro
from .analyze import Analyzer, RefusalError
from .artifacts import require_thumbnail
from .config import SPEC_VERSION, Config, load_config
from .publish import publish_pair
from .state import Store
from .stories import StoryLedger
from .transcribe import Word, get_transcript, hhmmss

log = logging.getLogger("boydclips")

VERTICAL_DIRECTIVE_FIELDS = {
    "hook_text", "top_output_s", "bottom_output_s", "top_crop", "bottom_crop", "direction_model",
}


def producer_cache_is_current(
    cached_material: Any,
    cached_plan: Any,
    cached_signature: Any,
    material: dict[str, Any],
    context: stage_context.StageContext,
    transcript: Transcript,
) -> bool:
    """Whether a saved Producer plan may be reused for this run.

    The plan is keyed by the source material *and* by the current rule context.
    A plan written before the rule handoff existed has no signature, so it is a
    miss rather than being restamped with today's rules; the cache records what
    this run actually planned against, and nothing older.
    """
    if cached_material != material:
        return False
    if cached_signature != context.cache_signature():
        return False
    return not producer_brain.validate_plan(cached_plan, material, transcript)


def validate_vertical_directive(directive: Any, configured_model: str) -> dict[str, Any]:
    """Accept a Short-thumbnail recipe only from the configured production brain.

    2026-09-16: this compared against the literal "gpt-5.6-sol". That named an
    unreachable brain, so a recipe the configured model actually produced was
    refused before it could be built. The rule is "the configured model directed
    it, and no stage substituted another one" — a record naming anything else
    still refuses, Sol included.
    """
    data = dict(directive)
    missing = sorted(VERTICAL_DIRECTIVE_FIELDS - set(data))
    if missing:
        raise ValueError(f"approved vertical thumbnail directive invalid; missing={missing}")
    got = str(data.get("direction_model") or "")
    if got != configured_model:
        raise ValueError(
            "approved vertical thumbnail directive was directed by "
            f"{got or 'an unrecorded model'}, not the configured {configured_model}"
        )
    return data


class TooShortError(RuntimeError):
    """The case is under the long-form floor once dead air is removed.

    Raised before the encode. run_daily() already treats a production failure
    as "skip this case, keep the docket pending", which is the right handling:
    a case that is mostly silence is not a failure of the run, it is a case
    that should not be published.
    """


class EditorialHoldError(RuntimeError):
    """The evidence says this case should stay unproduced for now."""


class StoryReuseError(RuntimeError):
    """The story already has work on record, and no revisit reason was given.

    2026-09-16: `dAKO7myCd-g:8929` was rendered although the same hearing already
    had a long-form and a Short (case 8340). Case keys could not see it — a
    re-scored hearing produces a new `<video>:<start>` row. The story ledger can,
    and this error is what stops the render before a single byte is downloaded.
    """


class DailyRunError(RuntimeError):
    """Viable work existed, but no complete review bundle was produced."""


class PausedError(RuntimeError):
    """The tray switch is RED. See tools/boyd-toggle.ps1."""


class JudgeSourceNotVerified(judges.RegistryError):
    """A judge profile has no court-owned direct source to discover from.

    Raised by ``Pipeline.discover_judge`` for a search-only profile (Simpson,
    Fleischer). A query is a lead, and the hits it returns for these judges are
    edited competitor clips, so scanning one would produce dockets that look
    like courtroom sources and are not. Subclasses judges.RegistryError — and
    therefore ValueError — so an existing caller that catches either still
    sees the refusal.
    """


def _docket_meta(docket: discover.Docket) -> dict[str, Any]:
    """Source metadata for the analyzer calls, built from one docket.

    The three original keys are always present and unchanged, so historical
    fixtures and prompt templates keep working. judge_id/judge_name ride along
    only when the docket actually carries them (``Docket`` always does now;
    getattr keeps a duck-typed stand-in from breaking the call).
    """
    meta: dict[str, Any] = {
        "title": docket.title,
        "docket_date": docket.docket_date,
        "url": docket.url,
    }
    judge_id = getattr(docket, "judge_id", "")
    judge_name = getattr(docket, "judge_name", "")
    if judge_id:
        meta["judge_id"] = judge_id
    if judge_name:
        meta["judge_name"] = judge_name
    return meta


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
        self._thumbnail_images_remaining = int(
            self.cfg.require("output.max_thumbnail_images_per_run")
        )
        self._thumbnail_model_calls_used = 0

    @property
    def analyzer(self) -> Analyzer:
        # Deferred so `discover`/`stats` work without any credential present.
        if self._analyzer is None:
            self._analyzer = Analyzer(self.cfg, log=log)
        return self._analyzer

    def close(self) -> None:
        self.store.close()

    # ------------------------------------------------------------------ stages

    def discover(self) -> list[discover.Docket]:
        found = discover.list_recent(
            self.cfg.require("source.channel_url"),
            self.cfg.get("source.scan_depth", 8),
        )
        # Skip only dockets that actually finished. Filtering on "have I seen
        # this row" would consume a docket the moment it was discovered, so a
        # dry run or any mid-run failure would retire it permanently.
        seen = {d.video_id for d in found if self.store.is_terminal(d.video_id)}
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

    def discover_judge(self, judge_id: str) -> list[discover.Docket]:
        """Explicit local discovery for one registered judge profile.

        Reads config/judges.yaml and lists that profile's own court-owned
        channel, stamping every docket with the judge it came from. Read-only
        by design: it does not touch the state DB, because nothing downstream
        (framing, identity, prompts, packaging) is profile-aware yet, and a
        stored row would be picked up later as if it were a Boyd docket.

        The daily ``discover()`` above is untouched — it stays pinned to
        config source.channel_url and the ordinary Boyd path, and
        ``production_enabled`` is not consulted here either: West is
        production-disabled and still discoverable, Simpson and Fleischer are
        refused because their only entries are unverified search queries.
        """
        profile = judges.get_profile(judge_id)          # JudgeNotFound if unknown
        urls = profile.court_source_urls
        if not urls:
            raise JudgeSourceNotVerified(
                f"judge profile {profile.id!r} has no court-owned direct source; "
                "only court-owned channels can be discovered (a search query is "
                "a lead, not a source)"
            )
        dockets = discover.list_recent(
            urls[0],
            self.cfg.get("source.scan_depth", 8),
            judge_id=profile.id,
            judge_name=profile.display_name,
        )
        log.info("discover_judge: %s — %d streams listed from %s",
                 profile.id, len(dockets), urls[0])
        return dockets

    def analyze_docket(self, docket: discover.Docket) -> list[dict[str, Any]]:
        work = self.work / docket.video_id
        work.mkdir(parents=True, exist_ok=True)

        cached = work / "scored.json"
        rubric_version = analyze.current_rubric_version()
        scored = None
        if cached.exists():
            payload = json.loads(cached.read_text(encoding="utf-8"))
            scored, why = analyze.score_cache_load(payload, rubric_version)
            if scored is None:
                # A cache from another editorial version is stale, not a
                # warning: it is re-scored below rather than ranked against
                # the current tiers (BOYD_EDITORIAL_V2 stabilisation).
                log.warning("  analysis: cache is stale (%s) — re-scoring under %s",
                            why, rubric_version)
        if scored is not None:
            # Re-assert the DB rows on every cache hit.
            #
            # This path used to return early, before save_case(). If the JSON
            # existed but the rows didn't — a crash between the two writes, or
            # a rebuilt DB — the cases were invisible to `boyd bank` and
            # `boyd run --case` forever, because analysis never ran again to
            # create them. save_case is INSERT OR REPLACE, so re-asserting is
            # free and idempotent.
            existing = {r["case_key"] for r in self.store.cases_for_docket(docket.video_id)}
            if len(existing) < len(scored):
                for case in scored:
                    self.store.save_case(docket.video_id, case, case.get("rank"))
                log.info("  analysis: reusing cached result (restored %d DB row(s))",
                         len(scored) - len(existing))
            else:
                log.info("  analysis: reusing cached result")
            return scored

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

        meta = _docket_meta(docket)

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

        cached.write_text(
            json.dumps(analyze.score_cache_dump(scored, rubric_version), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # BOYD_EDITORIAL_V2 PART 15 — a human-readable sidecar beside scored.json
        # so "why did it pick this" is one file, not a log grep. Additive.
        try:
            from . import editorial
            blocks = [f"# Editorial rationale — {docket.video_id} ({docket.docket_date})\n"
                      f"ruleset {editorial.RULESET} · prompt {self.analyzer.prompt_versions.get('score_cases', '?')}\n"]
            for case in scored:
                head = (f"## {hhmmss(case['start_s'])}–{hhmmss(case['end_s'])} "
                        f"{case.get('defendant_name', '?')} — {case.get('decision', '?')}"
                        f"{' · rank ' + str(case['rank']) if case.get('rank') else ''}")
                blocks.append(head + "\n\n```\n" + editorial.rationale_block(case) + "\n```\n")
            (work / "editorial_rationale.md").write_text("\n".join(blocks), encoding="utf-8")
        except Exception as exc:  # the sidecar must never break the run
            log.warning("  editorial rationale sidecar not written: %s", exc)
        self.store.mark_docket(docket.video_id, "analyzed", analyzed_at=_now())
        for case in scored:
            self.store.save_case(docket.video_id, case, case.get("rank"))
        return scored

    def produce(self, docket: discover.Docket, case: dict[str, Any], *,
                prepared_plan: dict[str, Any] | None = None,
                source_media: tuple[Path, float] | None = None) -> dict[str, Any]:
        """Download, cut, caption, and package one selected case."""
        work = self.work / docket.video_id
        case_key = self.store.case_key(docket.video_id, case["start_s"])

        # STORY-LEVEL MEMORY, before anything expensive (no download, no model
        # call, no render). A candidate is not new just because its row is: the
        # same hearing re-scored gets a second case key, and a story can carry
        # several of them (dAKO7myCd-g: 8320, 8340, 8929).
        self._story_memory(docket, case)
        # The folder name must include the case, not just the docket.
        #
        # It was "{date}_{video_id}", which is one folder per DOCKET — but a
        # docket routinely yields seven eligible cases, and each one silently
        # overwrote the last. Observed 2026-08-10: rendering Almaguer destroyed
        # a completed De Hoyos long-form and short with no warning, and the
        # manifest simply reported the survivor. Across an unattended backfill
        # that is a lot of quiet data loss.
        #
        # start_s is what distinguishes cases within a docket, and it is the
        # same value the case_key is built from, so the folder and the DB row
        # stay in step.
        stamp = (f"{docket.docket_date or 'undated'}_{docket.video_id}"
                 f"_{int(round(case['start_s']))}")
        review_dir = self.out / "review" / stamp
        review_dir.mkdir(parents=True, exist_ok=True)

        # Same options as the analysis stage. Normally the cache makes this a
        # no-op, but on a cache miss the defaults would quietly re-transcribe
        # with settings the config had disabled.
        transcript = get_transcript(
            docket.video_id,
            work,
            source=self.cfg.get("transcription.source", "auto_captions"),
            language=self.cfg.get("transcription.language", "en"),
            whisper_fallback=self.cfg.get("transcription.whisper_fallback", True),
            whisper_model=self.cfg.get("transcription.whisper_model", "medium"),
        )
        meta = _docket_meta(docket)

        lf_cfg = self.cfg.require("output.longform")
        sh_cfg = self.cfg.require("output.short")

        pad_before = lf_cfg.get("pad_before_s", 4.0)
        pad_after = lf_cfg.get("pad_after_s", 3.0)

        # A recessed-and-recalled hearing is one case in several sittings; the
        # long-form has to carry all of them or it ends on the recess with the
        # ruling missing. See Store.case_windows.
        windows = case.get("story_windows") or self.store.case_windows(docket.video_id, case["start_s"]) or [
            (case["start_s"], case["end_s"])
        ]
        # Segmentation sees ten-second transcript lines, so a final boundary can
        # land several seconds before the closing acknowledgment. When the next
        # case is known and close, extend only into that bounded gap. This keeps
        # the full ending without crossing into the next defendant.
        next_start = self.store.next_case_start(docket.video_id, windows[-1][0])
        final_start, final_end = windows[-1]
        boundary_cap = None
        if next_start is not None and 1.0 <= next_start - final_end <= 12.0:
            boundary_cap = next_start - 1.0
            windows[-1] = (final_start, boundary_cap)

        # Packaging runs AFTER the sittings are merged, not before.
        #
        # It used to run first, so `package()` only ever saw the first sitting
        # and the title and description described a case that had not finished.
        # Thompson's shipped description stopped at "so the claim could be
        # checked" — never mentioning that nothing was found or that he got
        # five years, both of which are in sitting 2. 20 cases in the bank are
        # split this way, so this was not a one-off.
        #
        # The case handed to the packager spans the first sitting's start to
        # the last sitting's end; `transcript.text_between` then covers every
        # sitting, and the recess gap between them costs a little transcript
        # the model can see but does not act on.
        story_case = dict(case)
        story_case["start_s"] = windows[0][0]
        story_case["end_s"] = windows[-1][1]
        story_case["story_windows"] = [[float(start), float(end)] for start, end in windows]

        lf_windows = []
        for index, (start, end) in enumerate(windows):
            padded_end = end + pad_after
            if boundary_cap is not None and index == len(windows) - 1:
                padded_end = min(padded_end, boundary_cap)
            lf_windows.append((max(0.0, start - pad_before), padded_end))
        lf_start = lf_windows[0][0]
        lf_end = lf_windows[-1][1]
        used_s = sum(e - s for s, e in lf_windows)

        if len(lf_windows) > 1:
            log.info(
                "  case: %d sittings — %s (recessed and recalled; all are rendered)",
                len(lf_windows),
                ", ".join(f"{hhmmss(s)}–{hhmmss(e)}" for s, e in lf_windows),
            )

        log.info(
            "  download: section %s–%s (%.1f min span, %.1f min used, "
            "not the full %.1f hr stream)",
            hhmmss(lf_start), hhmmss(lf_end),
            (lf_end - lf_start) / 60, used_s / 60, docket.duration_s / 3600,
        )
        if source_media is None:
            source, offset = render.download_section(
                docket.video_id, lf_start, lf_end, work / f"{case_key.replace(':', '_')}.mp4"
            )
        else:
            source, offset = Path(source_media[0]).resolve(), float(source_media[1])
            info = readiness.probe_video(source)
            if offset > lf_start or offset + info["duration_s"] < lf_end:
                raise ValueError("resumed source does not cover the full hearing render window")

        if self.cfg.get("analysis.producer_brain.enabled", True):
            log.info("  producer: building one evidence-grounded story and three packaging pairs")
            visual_evidence = thumbnail.producer_visual_evidence(
                source, offset, story_case, review_dir / "producer_frames",
            )
            transcript_path = work / f"{docket.video_id}.transcript.json"
            material = producer_brain.material_from_pipeline(
                case_key,
                story_case,
                meta,
                transcript,
                transcript_path,
                visual_evidence=visual_evidence,
            )
            plan = prepared_plan
            if plan is not None:
                errors = producer_brain.validate_plan(plan, material, transcript)
                if errors:
                    raise ValueError("prepared Producer plan failed current validation: " + "; ".join(errors))
                self.analyzer.prompt_versions[producer_brain.PROMPT_NAME] = producer_brain.PROMPT_VERSION
            # The current rules are read now, fresh, not at import: the same
            # call that feeds the model decides whether the cache still holds.
            rules_context = stage_context.load_context()
            plan_context_known = prepared_plan is None
            saved_input = review_dir / "producer_input.json"
            saved_plan = review_dir / "producer_plan.json"
            saved_context = review_dir / "producer_context.json"
            if plan is None and saved_input.is_file() and saved_plan.is_file():
                cached_material = json.loads(saved_input.read_text(encoding="utf-8"))
                cached_plan = json.loads(saved_plan.read_text(encoding="utf-8"))
                cached_signature = (
                    json.loads(saved_context.read_text(encoding="utf-8")).get("cache_signature")
                    if saved_context.is_file() else None
                )
                if producer_cache_is_current(
                    cached_material, cached_plan, cached_signature,
                    material, rules_context, transcript,
                ):
                    plan = cached_plan
                    self.analyzer.prompt_versions[producer_brain.PROMPT_NAME] = producer_brain.PROMPT_VERSION
                    log.info(
                        "  producer: reusing current validated plan for unchanged source "
                        "material and unchanged current rules"
                    )
            if plan is None:
                plan = self.analyzer.producer_plan(material, transcript)
                actual_context = getattr(self.analyzer, "last_producer_context", None)
                plan_context_known = actual_context is not None
                if actual_context is not None:
                    rules_context = actual_context
            if plan["video_decision"]["decision"] != "MAKE":
                raise EditorialHoldError(
                    f"Producer Brain {plan['video_decision']['decision']}: "
                    f"{plan['video_decision']['limitation']}"
                )
            if plan["short_plan"]["decision"] != "MAKE":
                raise EditorialHoldError(
                    f"Shorts Brain {plan['short_plan']['decision']}: "
                    f"{plan['short_plan']['limitation']}"
                )
            story_case["producer_short_plan"] = plan["short_plan"]
            pkg = producer_brain.package_from_plan(plan)
            (review_dir / "producer_input.json").write_text(
                json.dumps(material, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            (review_dir / "producer_plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            # Written beside the plan, never into it: the plan and its input
            # keep their existing schema, and an older review directory without
            # this sidecar stays a cache miss instead of being restamped.
            (review_dir / "producer_context.json").write_text(
                json.dumps(
                    {
                        "cache_signature": rules_context.cache_signature() if plan_context_known else None,
                        "stage_context": rules_context.provenance() if plan_context_known else None,
                        "provenance_status": "recorded" if plan_context_known else "unverified_prepared_plan",
                    },
                    ensure_ascii=False, indent=2, sort_keys=True,
                ) + "\n",
                encoding="utf-8",
            )
            (review_dir / "PRODUCER_REPORT.md").write_text(
                producer_brain.render_report(plan), encoding="utf-8",
            )
        else:
            log.info("  package: legacy one-pair packaging")
            pkg = self.analyzer.package(transcript, story_case, meta, SPEC_VERSION)
        if not pkg["hook_verified"]:
            log.warning(
                "  package: hook line not found verbatim in transcript — "
                "CONTENT_SPEC §6 requires titles the clip proves. Flagging for review."
            )
        pkg["tags"] = metadata.case_tags(
            self.cfg.get("packaging.longform.tags", []), story_case, pkg,
        )

        crop = None
        bg_crop = None
        if sh_cfg.get("autocrop", True):
            crop = render.detect_content_crop(source)
            log.info("  framing: %s", f"letterbox stripped -> {crop}" if crop
                     else "no baked-in letterbox detected")
            # A backdrop can use a crop the foreground cannot — see render_short.
            bg_crop = crop or render.detect_content_crop(source, min_agreement=0.25)
            if bg_crop and not crop:
                log.info("  framing: backdrop de-letterboxed -> %s", bg_crop)

        # CONTENT_SPEC §2: "Dead air longer than 4 seconds is removed. Shorter
        # gaps stay — courtroom pauses carry weight and cutting them makes
        # proceedings feel falsified."
        #
        # This was implemented in render.detect_silences/plan_silence_trim and
        # used only by scripts/build_thompson_longform.py — the daily path
        # concatenated the raw sitting windows and shipped them. Measured on
        # the render that path produced: 179.6s of silence in runs over 4s
        # across 838s (21.4%), including a 75s run, and it opened on 4.8s of
        # nothing. Every automated long-form was rendered against the spec
        # rather than to it. The one-off script is now the pipeline's
        # behaviour, with its constants and its refusals.
        lf_pieces = [render.Segment(s, e) for s, e in lf_windows]
        court_call_s = None
        if lf_cfg.get("start_at_court_call", True):
            lf_pieces, court_call_s = render.align_body_to_court_call(
                transcript.words,
                lf_pieces,
                max_wait_s=float(lf_cfg.get("court_call_max_wait_s", 90.0)),
                lead_s=float(lf_cfg.get("court_call_lead_s", 0.08)),
            )
            if court_call_s is not None:
                log.info("  opening: body aligned to 'court is calling' at %.2fs", court_call_s)
            else:
                log.warning("  opening: no 'court is calling' found in the opening window; original start kept")
        raw_s = sum(p.duration for p in lf_pieces)

        if lf_cfg.get("trim_dead_air", True):
            dead_air_s = float(lf_cfg.get("dead_air_s", 4.0))
            silences = render.detect_silences(
                source,
                noise_db=float(lf_cfg.get("silence_noise_db", -30.0)),
                min_silence_s=dead_air_s,
            )
            lf_pieces = render.plan_silence_trim(
                lf_pieces, silences, offset,
                min_silence_s=dead_air_s,
                # A hard zero-length join between two rooms of silence reads as
                # a glitch; a third of a second reads as an edit.
                keep_s=float(lf_cfg.get("silence_keep_s", 0.35)),
                # Looser than on a short deliberately: at 1.0s this refused a
                # legitimate cut because the fragment between two dead runs was
                # 0.80s, and a 6.5s dead run survived into an 11-minute video.
                min_piece_s=float(lf_cfg.get("silence_min_piece_s", 0.5)),
                edge_keep_s=0.05,
            )
            kept_s = sum(p.duration for p in lf_pieces)
            log.info(
                "  trim: dead air >%.0fs removed — %.0fs -> %.0fs (-%.0fs, %.1f%%) "
                "across %d pieces",
                dead_air_s, raw_s, kept_s, raw_s - kept_s,
                (100 * (raw_s - kept_s) / raw_s) if raw_s else 0.0, len(lf_pieces),
            )

        planned_s = sum(p.duration for p in lf_pieces)

        # The min/max duration bounds were documented in config and enforced
        # nowhere — STATE.md flagged the 1200s cap as unenforced and a 33.9
        # minute long-form went through it. Checked before the encode, because
        # the encode is the expensive part.
        floor_s = float(lf_cfg.get("min_duration_s", 120))
        cap_s = float(lf_cfg.get("max_duration_s", 1200))

        # A MOMENT is a short, not a long-form, so the long-form floor does not
        # apply to it. See claude/MOMENTS.md: the unit is the 30-60 seconds
        # where she goes off, and 58 seconds failing a 120-second floor is the
        # floor being asked the wrong question, not the clip being too short.
        #
        # The long-form is still written — it is the same cut, unpadded — so
        # every downstream consumer (thumbnail, manifest, publish ordering)
        # keeps working. What a moment CANNOT do is carry the long-form half of
        # the funnel on its own; stitching several into a compilation is the
        # open product question, recorded in MOMENTS.md.
        is_moment = case.get("source") == "moments"
        if planned_s < floor_s and not is_moment:
            raise TooShortError(
                f"{case_key}: {planned_s:.0f}s after trimming is under the "
                f"{floor_s:.0f}s floor — nothing rendered"
            )
        if planned_s < floor_s:
            log.info("  render: %.0fs moment — long-form floor of %.0fs does not "
                     "apply, this is a short", planned_s, floor_s)
        # Story-preserving cap (2026-09-06, src/boydclips/capfit.py). The old
        # walk kept pieces in order until the budget ran out, which dropped the
        # TAIL — the ruling, the payoff the case was selected for. Now the
        # setup, the money-moment window and the ending are protected and the
        # rest is spent nearest-to-the-story first. If the protected story
        # itself does not fit, CapFitError is raised and run_daily skips the
        # case with the reason (last fallback) — nothing is truncated silently.
        cap_plan = None
        if planned_s > cap_s:
            gaps = capfit.word_gaps(transcript.words, lf_start, lf_end)
            cap_plan = capfit.plan_cap_fit(lf_pieces, cap_s, case, lf_cfg.get("cap_fit") or {}, gaps=gaps)
            lf_pieces = cap_plan.pieces
            planned_s = sum(p.duration for p in lf_pieces)
            for line in capfit.describe(cap_plan).splitlines():
                log.warning("  render: %s", line)

        starts = [p.start_s for p in lf_pieces]
        if starts != sorted(starts):
            raise ValueError(
                f"{case_key}: long-form pieces are out of chronological order — "
                "refusing to render reordered proceedings (CONTENT_SPEC §2)"
            )

        # The branded sting. render_longform has accepted an `intro` since it
        # was written and nothing ever passed one, so every automated long-form
        # went out unbranded — the same silent-degradation shape as the missing
        # watermark and the missing thumbnail.
        #
        # NOTE, deliberately recorded: CONTENT_SPEC §2 specifies a cold open
        # with "no intro, no branding". Nathan asked for the sting on
        # 2026-08-17 and that governs, but the spec now disagrees with the
        # build and one of the two should be amended.
        intro = None
        if lf_cfg.get("intro_enabled", True):
            intro = render.resolve_intro(lf_cfg.get("intro_path"))
            if intro is None:
                raise RuntimeError("intro is enabled but no sting was found; restore the asset or explicitly disable the intro")
            else:
                log.info("  render: intro %s", intro.name)

        # R49 cold open ("Coming up..."): the money moment, labelled, before the
        # sting. render_longform has rendered it since 2026-09-02 and the posted
        # long-forms carried it through the manual chain; the daily route never
        # passed one. The span comes from the same money moment capfit protects.
        coldopen = None
        coldopen_note = "disabled"
        if intro is not None and lf_cfg.get("coldopen_enabled", True):
            producer = pkg.get("producer_brain") or {}
            if producer:
                opening = producer["cold_open"]
                coldopen = (float(opening["start_s"]), float(opening["end_s"]))
                if not any(a <= coldopen[0] < coldopen[1] <= b for a, b in windows):
                    raise ValueError("Producer cold open leaves the authorized hearing")
                lf_cfg = {**lf_cfg, "coldopen_min_s": 5.0, "coldopen_max_s": 12.0}
                coldopen_note = "validated Producer Brain cold_open"
                mm_src = "producer_brain.cold_open"
            else:
                mm, mm_src = capfit.resolve_money_moment(story_case, lf_start, lf_end)
                coldopen, coldopen_note = render.coldopen_span(transcript.words, mm, lf_pieces)
            if coldopen is not None:
                log.info("  render: cold open %.1f-%.1f (%.1fs) from %s",
                         coldopen[0], coldopen[1], coldopen[1] - coldopen[0], mm_src)
            else:
                log.warning("  render: cold open skipped: %s", coldopen_note)

        log.info("  render: long-form (%d pieces, %.0fs)", len(lf_pieces), planned_s)
        lf_path = review_dir / "longform.mp4"
        lf_duration = render.render_longform(
            source, offset, lf_pieces, lf_cfg, lf_path, crop=crop, intro=intro,
            coldopen=coldopen,
        )
        lf_clip_id = self.store.save_clip(
            case_key, "longform", lf_path, lf_duration,
            pkg["longform_title"], "", SPEC_VERSION,
        )

        lf_description = self.cfg.require("packaging.longform.description_template").format(
            summary=pkg["summary"],
            proceeding_type=_proceeding_label(case["proceeding_type"]),
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
                "tags": pkg["tags"],
                # Story-preserving cap plan (None when the case fit the cap).
                # Rides into the manifest under outputs.longform so the kept /
                # dropped ranges are auditable per clip.
                "cap_fit": cap_plan.as_dict() if cap_plan else None,
                # R49 cold open actually rendered (span None = skipped, with the reason).
                "coldopen": {"span": list(coldopen) if coldopen else None, "note": coldopen_note},
                "source_timeline": {
                    "source_path": str(source.resolve()), "source_sha256": readiness.sha256_file(source),
                    "offset_s": offset,
                    "segments": [[piece.start_s, piece.end_s] for piece in lf_pieces],
                    "court_call_start_s": court_call_s,
                    "intro_path": str(intro) if intro else None,
                    "intro_duration_s": render.probe_duration(intro) if intro else 0.0,
                },
            },
            "short": None,
        }

        # A long-form requires its thumbnail even when no short can be made.
        result["thumbnail"] = self._produce_thumbnail(source, offset, story_case, pkg, review_dir)
        # SHORTS_EDITOR_V2 plans the short as a mini-story and refuses with a
        # reason; `output.short.editor: legacy` restores the model-beat path
        # unchanged for rollback.
        editor = str(sh_cfg.get("editor", "v2")).lower()
        if editor == "legacy":
            self._short_legacy(source, offset, story_case, case_key, pkg, review_dir,
                               sh_cfg, crop, bg_crop, transcript, result)
        else:
            self._short_v2(source, offset, story_case, case_key, pkg, review_dir,
                           sh_cfg, crop, bg_crop, transcript, result)
        self._write_manifest(review_dir, docket, story_case, pkg, result)
        return result

    # ------------------------------------------------------------ short: V2

    def _short_v2(self, source: Path, offset: float, case: dict[str, Any], case_key: str,
                  pkg: dict[str, Any], review_dir: Path, sh_cfg: dict[str, Any],
                  crop: str | None, bg_crop: str | None, transcript: Any,
                  result: dict[str, Any]) -> None:
        """SHORTS_EDITOR_V2: plan a contiguous mini-story, refuse explicitly,
        render on the FIXED 50/50 courtroom layout with subject-centred tiles
        and punch-ins inside the tile, captions on the divider rail, no end
        card, then QC the file and its composition.

        SAME-CASE GUARANTEE. The plan is built from this case's own span of
        the transcript and bound to `case_key`; verify_same_case(),
        verify_chronology() and verify_continuity() re-check the binding,
        the ranges, the order and every interior join right before the
        render, and the manifest carries outputs.short.source_case_key plus
        the whole edit plan.
        """
        from . import captions, layout, shorts_editor
        sh_cfg = dict(sh_cfg)
        pcfg = dict(sh_cfg.get("planner") or {})
        pcfg.setdefault("max_duration_s", sh_cfg.get("max_duration_s", 59))
        w_px, h_px = sh_cfg.get("resolution", [1080, 1920])
        pcfg["canvas_h"] = int(h_px)
        # the V2 caption style: the shared caption keys, overridden by `rail`
        cap_cfg = dict(sh_cfg.get("captions", {}))
        cap_cfg.update(dict(cap_cfg.pop("rail", {}) or {}))
        cap_cfg = captions.resolve_style(cap_cfg)
        short_case = dict(case)
        brain_plan = case.get("producer_short_plan") or {}
        brain_sequence = list(brain_plan.get("sequence") or [])
        if brain_sequence:
            pcfg["producer_preserve_ranges"] = [
                [float(row["start_s"]), float(row["end_s"])] for row in brain_sequence
            ]
            short_case["start_s"] = min(float(row["start_s"]) for row in brain_sequence)
            short_case["end_s"] = max(float(row["end_s"]) for row in brain_sequence)
            short_case["short_segments"] = [
                {
                    "beat": str(row.get("role") or "moment"),
                    "start_s": float(row["start_s"]),
                    "end_s": float(row["end_s"]),
                    "quote": str(row.get("quote") or ""),
                }
                for row in brain_sequence
            ]
            short_case["hook_quote"] = str(brain_plan.get("hook") or "")
            short_case["hook_start_s"] = float(brain_plan.get("hook_start_s") or short_case["start_s"])
            short_case["editorial"] = dict(short_case.get("editorial") or {})
            payoff_row = next(
                (row for row in reversed(brain_sequence)
                 if str(row.get("role") or "").lower() in {"payoff", "decision", "outcome", "consequence"}),
                brain_sequence[-1],
            )
            short_case["editorial"]["money_moment"] = str(
                payoff_row.get("quote") or brain_plan.get("payoff") or short_case["hook_quote"]
            )
            short_case["editorial"]["money_moment_s"] = float(payoff_row["start_s"])
            result.setdefault("short_editor", {})["producer_brain_source"] = {
                "decision": brain_plan.get("decision"),
                "chronology_strategy": brain_plan.get("chronology_strategy"),
                "hook": brain_plan.get("hook"),
                "hook_start_s": brain_plan.get("hook_start_s"),
                "hook_end_s": brain_plan.get("hook_end_s"),
                "payoff": brain_plan.get("payoff"),
                "sequence": brain_sequence,
            }

        def _record(plan: Any, tile_map: dict[str, Any]) -> None:
            plan_data = plan.as_dict()
            (review_dir / "short_plan.txt").write_text(shorts_editor.describe(plan), encoding="utf-8")
            (review_dir / "short_plan.json").write_text(
                json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")
            result.setdefault("short_editor", {})
            result["short_editor"].update({
                "ruleset": shorts_editor.RULESET, "ok": plan.ok, "refusal": plan.refusal,
                "total": plan.total, "scores": plan.scores, "case_key": case_key,
                "anchor": plan.anchor, "tile_map": tile_map,
                "source_segments": plan_data.get("segments") or [],
            })
            if brain_plan:
                result["short_editor"]["producer_alignment"] = shorts_editor.producer_alignment(plan, brain_plan, transcript.words)
            if case.get("shortable") and not plan.ok:
                log.warning("  short: MISMATCH — the scorer marked the case shortable; %s found no valid mini-story",
                            shorts_editor.RULESET)
                result["short_editor"]["mismatch_with_scorer"] = "scorer said shortable; planner refused"
            elif plan.mismatch_with_scorer:
                log.info("  short: %s", plan.mismatch_with_scorer)
                result["short_editor"]["mismatch_with_scorer"] = plan.mismatch_with_scorer

        # 1. Plan on the transcript alone first. This touches no media, so a
        #    case with no mini-story costs nothing.
        pre = shorts_editor.plan_short(short_case, case_key, transcript.words, pcfg, cap_cfg)
        if not pre.ok:
            # Auto-captions with no '>>' markers and no punctuation (the 2024
            # dockets) give the text splitter one turn; the diarised pass below
            # can still read the hearing, so the refusal is deferred to it.
            case_words = [
                w for w in transcript.words
                if short_case["start_s"] <= w.t <= short_case["end_s"]
            ]
            if shorts_editor.has_speaker_structure(case_words):
                _record(pre, {})
                log.info("  render: no short — %s", pre.refusal)
                return
            log.info("  short: transcript has no speaker structure (no '>>' markers, no punctuation) — "
                     "deferring the plan to diarisation (%s)", pre.refusal)

        # 2. The two tiles and which one is hers. The fixed layout NEEDS both
        #    tiles; a source they cannot be measured on is refused with the
        #    reason (the long-form still ships).
        tiles = None
        tile_map: dict[str, Any] = {}
        try:
            tiles = render.detect_tile_crops(source)
        except Exception as exc:
            log.warning("  framing: tile detection failed (%s)", exc)
        if tiles:
            tile_map = self._judge_tile_map(source, offset, case, tiles, sh_cfg, review_dir)
            sh_cfg["vertical_mode"] = "duo_fill"
            log.info("  framing: fixed 50/50 — top %s | bottom %s; Boyd tile=%s (%s)",
                     tiles[0], tiles[1], tile_map.get("boyd"), tile_map.get("source"))
        else:
            pre.ok = False
            pre.refusal = "the two Zoom tiles could not be measured on this source; the fixed 50/50 layout needs both"
            _record(pre, {})
            log.info("  render: no short — %s", pre.refusal)
            return

        # 3. Speaker turns. Diarisation is advisory: the planner labels turns
        #    from the transcript and lets the ECAPA turns override Boyd /
        #    not-Boyd when they exist.
        diar = None
        try:
            raw = diarize.diarize(source)
            if raw:
                absolute_turns = [(t + offset, who) for t, who in raw]
                relevant_speakers = {
                    who for index, (start, who) in enumerate(absolute_turns)
                    if start < short_case["end_s"] and
                    (absolute_turns[index + 1][0] if index + 1 < len(absolute_turns) else float("inf")) > short_case["start_s"]
                }
                if len(relevant_speakers) <= 1 and shorts_editor.has_speaker_structure(
                    transcript.slice(short_case["start_s"], short_case["end_s"])
                ):
                    log.warning("  speakers: audio labels collapse this exchange to one speaker; using transcript turns")
                else:
                    diar = absolute_turns
                    log.info("  speakers: %d diarised turns", len(diar))
        except Exception as exc:
            log.warning("  speakers: diarisation unavailable (%s) — transcript labels only", exc)

        # 4. The plan, now with the tile map, diarised turns and measured silence.
        silences = []
        if brain_plan:
            silences = render.detect_silences(source, noise_db=-30.0, min_silence_s=0.30)
            pcfg["verified_audio_silences"] = [[a + offset, b + offset] for a, b in silences]
        plan = shorts_editor.plan_short(
            short_case, case_key, transcript.words, pcfg, cap_cfg, diar=diar,
            tile_map=tile_map if tile_map.get("boyd") else None,
        )
        _record(plan, tile_map)
        if not plan.ok:
            log.info("  render: no short — %s (%s)", plan.refusal,
                     "the transcript-only plan had passed; diarisation changed the read" if pre.ok
                     else "transcript-only plan refused too; diarisation did not rescue it")
            return
        # 2026-09-16: this is how a Short nobody wanted got rendered. When the
        # scorer calls a case shortable but the planner finds no mini-story in
        # it, a Producer plan can still hand over ranges that pass QC — the
        # ranges are exact, the captions are clean, and the result is lame,
        # because the case never had a Short in it. That now needs an explicit
        # override recorded on the plan itself; without one the run stops before
        # anything is rendered.
        forced = (not pre.ok and bool(case.get("shortable"))) or \
            result.get("short_editor", {}).get("mismatch_with_scorer") == "scorer said shortable; planner refused"
        if forced and not str(brain_plan.get("override") or "").strip():
            plan.ok = False
            plan.refusal = ("forced Producer plan: the planner found no mini-story for this case — "
                            "set short_plan.override to the reason this cut is still right, or pick another case")
            _record(plan, tile_map)
            log.error("  short: %s", plan.refusal)
            return
        shorts_editor.verify_same_case(plan, case_key, case)   # raises on any drift
        shorts_editor.verify_chronology(plan.as_dict())        # raises on any reorder
        cuts = shorts_editor.verify_continuity(plan, transcript.words, short_case, pcfg)  # raises on a false join
        if brain_plan:
            audio_checks = shorts_editor.producer_silence_checks(plan.segments, brain_plan, silences, offset)
            result["short_editor"]["silence_evidence"] = {
                "source_path": str(source.resolve()), "source_sha256": readiness.sha256_file(source),
                "offset_s": offset, "noise_db": -30.0, "min_silence_s": 0.30,
                "checks": audio_checks,
            }
            if any(not check["ok"] for check in audio_checks):
                plan.ok = False
                plan.refusal = "transcript gap is not verified audio silence; preserve or repair the source passage"
                _record(plan, tile_map)
                log.error("  short: %s", plan.refusal)
                return
        log.info("  continuity: %d interior join(s) audited, none skips substantive dialogue", len(cuts))
        log.info("  render: short (%s @%.0fs, %d beats, %.1fs, score %d/100, %s)",
                 plan.anchor.get("kind"), plan.anchor.get("t", 0.0), len(plan.beats),
                 plan.duration_s, plan.total, "declared teaser" if plan.nonlinear else "chronological")

        # 5. Subject anchors (measured faces) -> the composition, then the ONE
        #    overlay layout; a collision refuses the render before ffmpeg runs.
        anchors = self._subject_anchors(source, offset, plan, tiles, review_dir, tile_map)
        comp = layout.compose(plan.focus_plan, plan.punch_plan, tiles, tile_map, anchors, sh_cfg)
        # The "FULL VIDEO" call to action (src/boydclips/cta.py) is planned
        # here so its box is part of the ONE overlay layout: a collision with
        # the caption rail or the watermark refuses the render like any other.
        cta_place = self._plan_cta(source, offset, plan, comp, cap_cfg, sh_cfg, w_px, review_dir)
        overlay = layout.overlay_layout(cap_cfg, sh_cfg, self._watermark_size(sh_cfg, w_px),
                                        extra=[cta_place.box] if cta_place else None)
        checks = layout.composition_checks(comp, overlay)
        result["short_editor"]["composition"] = {k: v for k, v in comp.items() if not k.startswith("_")}
        result["short_editor"]["overlay"] = overlay
        result["short_editor"]["cta"] = cta_place.as_dict() if cta_place else {"enabled": False}
        result["short_editor"]["composition_checks"] = checks
        log.info("  layout: divider y=%d; top subject x=%.0f (%s); bottom subject x=%.0f (%s); punch %.2f on %s",
                 comp["divider_y"], comp["base"]["top"]["subject_x"], comp["anchors"]["top"]["source"],
                 comp["base"]["bottom"]["subject_x"], comp["anchors"]["bottom"]["source"], comp["punch_zoom"],
                 [s["punch"] for s in comp["segments"] if s["punch"]])
        log.info("  overlays: caption centre %s, boxes %s -> overlay_collision %s",
                 overlay["caption_center"], [(b["name"], b["x"], b["y"], b["w"], b["h"]) for b in overlay["boxes"]],
                 overlay["overlay_collision"])
        bad_layout = [c for c in checks if not c["ok"]]
        if not overlay["ok"] or bad_layout:
            result["short_editor"]["ok"] = False
            result["short_editor"]["refusal"] = "layout QC failed: " + "; ".join(
                [f"overlay {overlay['collisions']}"] if not overlay["ok"] else [] + [c["check"] for c in bad_layout])
            log.error("  short: %s", result["short_editor"]["refusal"])
            return

        # 6. Captions on the rail, from the EXACT words that survive the edit:
        #    transcript words mapped through the same segment list the
        #    renderer cuts (one timeline map), phrased as indices by
        #    captions.plan_phrases (deterministic, or a registered provider
        #    whose proposal is validated and otherwise ignored).
        ass_path = None
        stream = plan.word_stream                     # kept words + output times + verified speakers
        mapped = render.map_words_to_timeline(transcript.words, plan.segments, absorb_gap_s=0.0)
        if len([w for w in mapped if render.strip_caption_artifact(w.w)]) != len(stream):
            log.warning("  captions: word stream (%d) differs from the transcript mapped through the segments (%d)",
                        len(stream), len(mapped))
        hard_positions = shorts_editor.caption_hard_breaks(plan, stream)
        # caption_hard_breaks locates cuts in the edited stream; the caption
        # planner maps breaks from the original source-word indices.
        hard = {int(stream[pos]["i"]) for pos in hard_positions}
        cres = captions.plan_captions(stream, cap_cfg, sorted(hard), self._caption_provider(cap_cfg))
        cards, planner_used = cres["cards"], cres["planner_used"]
        cap_qc = captions.kinetic_qc(cards, cres["display"], cap_cfg, cres["hard_breaks"], cres["audit"])
        plan.captions = cards
        plan.caption_planner = planner_used
        plan.caption_hard_breaks = list(cres["hard_breaks"])
        plan.caption_audit = cres["audit"]
        plan.caption_density = cres["density"]
        result["short_editor"]["captions"] = {"planner": planner_used, "phrases": len(cards),
                                              "words": len(stream), "displayed": len(cres["display"]),
                                              "omitted": [{"i": a["i"], "w": a["w"], "reason": a["reason"]} for a in cres["omitted"]],
                                              "reveals": sum(len(c["events"]) for c in cards),
                                              "density": cres["density"],
                                              "qc": cap_qc, "width_source": captions.width_source(cap_cfg)}
        bad_caps = [g["gate"] for g in cap_qc if not g["ok"]]
        log.info("  captions: %d kept words, %d displayed (%d disfluencies omitted), %d one-line phrases (%s), "
                 "%d reveals, %.2f changes/s, rail %s, QC %s",
                 len(stream), len(cres["display"]), len(cres["omitted"]), len(cards), planner_used,
                 sum(len(c["events"]) for c in cards), cres["density"]["per_second"],
                 overlay["caption_center"], "PASS" if not bad_caps else "FAIL " + ",".join(bad_caps))
        if bad_caps:
            result["short_editor"]["ok"] = False
            result["short_editor"]["refusal"] = "caption QC failed: " + ", ".join(bad_caps)
            _record(plan, tile_map)
            log.error("  short: %s", result["short_editor"]["refusal"])
            return
        if cap_cfg.get("enabled", True):
            ass_path = review_dir / "captions.ass"
            # TRUE VISUAL CENTRING: predicted origins, then measured on a
            # black canvas with the real libass + fonts and corrected
            centering = render.calibrate_caption_positions(cards, cap_cfg, plan.duration_s, ass_path)
            result["short_editor"]["captions"]["visual_center"] = {
                k: centering[k] for k in ("predicted_max_error_px", "measured_before", "measured_after",
                                           "max_error_px", "mean_error_px", "rounds", "measured_phrases")}
            result["short_editor"]["captions"]["caption_visual_center_error_px"] = centering["max_error_px"]
            result["short_editor"]["captions"]["visual_center"]["vertical"] = centering["vertical_error_px"]
            result["short_editor"]["captions"]["visual_center"]["rail_y_offset"] = centering["rail_y_offset"]
            result["short_editor"]["captions"]["per_phrase_center"] = [
                {"text": m["text"], "center": m["center"], "error_px": m["error_px"]} for m in centering["per_card"]]
            log.info("  captions: visual centre error max %.1f px, mean %.2f px over %d phrases "
                     "(predicted max %.1f, before calibration max %.1f, %d correction round(s))",
                     centering["max_error_px"], centering["mean_error_px"], centering["measured_phrases"],
                     centering["predicted_max_error_px"], centering["measured_before"]["max_error_px"], centering["rounds"])
        _record(plan, tile_map)

        # 7. Render on the fixed stack — each camera graded on its own before
        #    assembly (output.short.color.<role>), the floor grade after.
        windows = [(seg.top.crop, seg.bottom.crop) for seg in comp["_segments"]]
        color_cfg = dict(sh_cfg.get("color") or {})
        role_top = "defendant" if tile_map.get("defendant") == "top" else "boyd"
        role_bottom = "boyd" if role_top == "defendant" else "defendant"
        tile_filters = (render.camera_grade_filter(color_cfg, role_top),
                        render.camera_grade_filter(color_cfg, role_bottom))
        result["short_editor"]["camera_grades"] = {
            "top": {"role": role_top, "filter": tile_filters[0] or "(none)"},
            "bottom": {"role": role_bottom, "filter": tile_filters[1] or "(none)"},
            "final": render.short_grade_filter(sh_cfg) or "(none)",
        }
        log.info("  grade: top=%s %s | bottom=%s %s | after assembly %s", role_top, tile_filters[0] or "(none)",
                 role_bottom, tile_filters[1] or "(none)", render.short_grade_filter(sh_cfg) or "(none)")
        # Visual polish (2026-09-06): a better tile scaler and a restrained
        # post-scale clarity pass per camera (output.short.clarity), applied
        # after each tile's scale and before the stack; captions burn in
        # after the stack so the text never passes through it.
        clarity_cfg = dict(sh_cfg.get("clarity") or {})
        tile_post = (render.camera_clarity_filter(clarity_cfg, role_top),
                     render.camera_clarity_filter(clarity_cfg, role_bottom))
        result["short_editor"]["clarity"] = {
            "scale_flags": clarity_cfg.get("scale_flags") or "(swscale default: bicubic)",
            "top": {"role": role_top, "filter": tile_post[0] or "(none)"},
            "bottom": {"role": role_bottom, "filter": tile_post[1] or "(none)"},
            "captions_after_clarity": True,
        }
        encode_policy = dict(sh_cfg.get("encode") or {"mode": "crf", "crf": sh_cfg.get("crf", 20)})
        result["short_editor"]["encode"] = {"codec": "libx264", "preset": str(encode_policy.get("preset", sh_cfg.get("preset", "medium"))),
                                            "policy": encode_policy, "pix_fmt": "yuv420p",
                                            "fps": sh_cfg.get("fps", 30), "resolution": sh_cfg.get("resolution", [1080, 1920])}
        log.info("  clarity: scale flags %s | top=%s %s | bottom=%s %s | encode libx264 %s crf %s",
                 clarity_cfg.get("scale_flags") or "bicubic", role_top, tile_post[0] or "(none)",
                 role_bottom, tile_post[1] or "(none)", sh_cfg.get("preset", "medium"), sh_cfg.get("crf", 20))
        # The CTA's frames and sound, built for THIS plan (cta/ beside the
        # render), then composited in the same ffmpeg pass.
        cta_rec = None
        if cta_place:
            cta_rec = cta.build_assets(cta_place, sh_cfg.get("cta"), review_dir / "cta", int(sh_cfg.get("fps", 30)),
                                       source=source, offset_s=offset, segments=plan.segments)
            result["short_editor"]["cta"]["assets"] = {k: v for k, v in cta_rec.items() if k in ("frames", "sound")}
            log.info("  cta: %s side, %.2f-%.2fs (%s), sfx gain %s dB",
                     cta_place.side, cta_place.start_s, cta_place.end_s,
                     "fades out" if cta_place.fade else "holds to the last frame",
                     (cta_rec.get("sound") or {}).get("gain_db", "off"))
        narration_directive = case.get("approved_narrated_intro")
        sh_path = review_dir / "short.mp4"
        body_path = review_dir / "short_body.mp4" if narration_directive else sh_path
        sh_duration = render.render_short(
            source, offset, plan.segments, sh_cfg, ass_path, body_path,
            crop=crop, bg_crop=bg_crop, tile_crops=windows[0] if windows else None, duo_punch=windows,
            duo_punch_filters=tile_filters, duo_punch_post=tile_post, cta=cta_rec,
        )
        concat_body_path = body_path
        if narration_directive:
            concat_body_path = review_dir / "short_body_48k.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(body_path), "-c:v", "copy",
                            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
                            str(concat_body_path)], check=True)
            sh_duration = render.probe_duration(concat_body_path)

        # 8. Loudness (tools/master_audio.py: -14 LUFS / -1.5 dBTP, video copied).
        loud = None if narration_directive else self._master_short_audio(body_path, sh_cfg)
        if loud and loud.get("duration_s"):
            sh_duration = float(loud["duration_s"])

        # 9. Render QC + visual QC — the file must match the plan, and the
        #    composition must be what the layout said (divider measured on
        #    the frames, normal and punched).
        qc = self._short_render_qc(concat_body_path, sh_duration, plan, sh_cfg)
        vqc = render.visual_qc(concat_body_path, plan.as_dict(), comp, overlay, checks, review_dir,
                               extra_frames=cta.review_frame_times(cta_place) if cta_place else None)
        result["short_editor"]["render_qc"] = qc
        result["short_editor"]["loudness"] = loud
        result["short_editor"]["visual_qc"] = {"contact_sheet": vqc.get("contact_sheet"), "ok": vqc.get("ok"),
                                               "checks": vqc.get("checks"), "frames": vqc.get("frames")}
        failed = [g["gate"] for g in qc if not g["ok"]] + [c["check"] for c in vqc.get("checks", []) if not c["ok"]]
        if failed:
            log.error("  short: QC failed — %s", "; ".join(failed))
            result["short_editor"]["ok"] = False
            result["short_editor"]["refusal"] = "render/visual QC failed: " + "; ".join(failed)
            return

        if narration_directive:
            intro_path, intro_record = self._render_approved_narrated_intro(
                source, offset, narration_directive, review_dir, sh_cfg
            )
            concat_file = review_dir / "narrated_short_concat.txt"
            hook_paths = [Path(row["normalized_path"]) for row in intro_record.get("source_hooks", [])]
            concat_parts = [*hook_paths, intro_path, concat_body_path]
            concat_file.write_text("\n".join(f"file '{part.as_posix()}'" for part in concat_parts) + "\n",
                                   encoding="utf-8")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                            "-c", "copy", "-movflags", "+faststart", str(sh_path)], check=True)
            transition_record = None
            hook_duration = sum(float(row["duration_s"]) for row in intro_record.get("source_hooks", []))
            body_output_start = hook_duration + float(intro_record["duration_s"])
            if intro_record.get("transition_sfx"):
                transition = intro_record["transition_sfx"]
                mixed_path = review_dir / "narrated_short_with_handoff_sfx.mp4"
                transition_record = narrated_short_intro.mix_transition_sfx(
                    sh_path,
                    mixed_path,
                    Path(transition["path"]),
                    body_output_start,
                    float(transition["gain_db"]),
                )
                mixed_path.replace(sh_path)
            sh_duration = render.probe_duration(sh_path)
            if sh_duration >= float(sh_cfg.get("max_duration_s", 59)):
                raise ValueError(f"narrated Short is {sh_duration:.3f}s, exceeds configured maximum")
            loud = self._master_short_audio(sh_path, sh_cfg)
            if loud and loud.get("duration_s"):
                sh_duration = float(loud["duration_s"])
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(sh_path), "-f", "null", "NUL"], check=True)
            result["short_editor"]["approved_narrated_intro"] = {
                **intro_record, "body_path": str(concat_body_path), "final_duration_s": sh_duration,
                "transition_sfx_mix": transition_record,
                "final_sha256": readiness.sha256_file(sh_path),
                "output_timeline": {"source_hooks_start_s": 0.0, "narration_start_s": hook_duration,
                                    "body_output_start_s": body_output_start,
                                    "final_end_s": sh_duration},
                "source_timeline": {"source_path": str(source.resolve()), "offset_s": offset,
                                    "body_segments": [[s.start_s, s.end_s] for s in plan.segments]},
            }

        sh_clip_id = self.store.save_clip(
            case_key, "short", sh_path, sh_duration, pkg["short_title"], "", SPEC_VERSION
        )
        result["short"] = {
            "clip_id": sh_clip_id,
            "file_path": str(sh_path),
            "title": pkg["short_title"],
            "description": "",  # filled after the long-form URL exists
            "duration_s": sh_duration,
            "source_case_key": case_key,
            "edit_plan": plan.as_dict(),
            "vertical_thumbnail_required": True,
            "vertical_thumbnail": None,
        }
        result["short"]["vertical_thumbnail"] = self._produce_short_vertical_thumbnail(
            sh_path, case.get("approved_vertical_thumbnail"), review_dir
        )

    def _subject_anchors(self, source: Path, offset: float, plan: Any, tiles: tuple[str, str],
                         review_dir: Path, tile_map: dict[str, Any] | None = None) -> dict[str, Any]:
        """Where each person sits in their tile, MEASURED: YuNet faces
        (tools/identity.faces_in — the detector the thumbnail path already
        trusts) on frames sampled inside the kept ranges, the largest face
        inside each tile per frame, the median over frames. One stable
        anchor per tile for the whole Short (no tracking, no jitter). When
        no face is found in a tile the geometric fallback is used and
        recorded as such."""
        from . import layout
        samples: list[float] = []
        for s in plan.segments:
            samples.append(s.start_s + min(0.5, s.duration / 2.0))
            if s.duration > 3.0:
                samples.append(s.start_s + s.duration / 2.0)
        samples = sorted(set(round(t, 2) for t in samples))[:10]
        rects = [layout.parse_crop(t) for t in tiles]
        found: dict[str, list[tuple[float, float, float, float]]] = {"top": [], "bottom": []}
        try:
            import sys as _sys
            tools = Path(__file__).resolve().parents[2] / "tools"
            if str(tools) not in _sys.path:
                _sys.path.insert(0, str(tools))
            import cv2  # noqa: WPS433
            import identity  # noqa: WPS433
            probe = review_dir / "_anchor_probe.jpg"
            for t in samples:
                frame = render.extract_thumbnail(source, max(0.0, t - offset), probe)
                bgr = cv2.imread(str(frame))
                if bgr is None:
                    continue
                rows = identity.faces_in(bgr, score=0.6)
                for name, (tw, th, tx, ty) in zip(("top", "bottom"), rects):
                    inside = []
                    for r in rows:
                        x, y, w, h = (float(v) for v in r[:4])
                        cx, cy = x + w / 2.0, y + h / 2.0
                        if tx <= cx <= tx + tw and ty <= cy <= ty + th:
                            inside.append((w, (cx - tx) / tw, (cy - ty) / th, w / tw, h / th))
                    role = "boyd" if (tile_map or {}).get("boyd") == name else "defendant"
                    pick = choose_subject_face(inside, role)
                    if pick:
                        _w, fx, fy, fw, fh = pick
                        found[name].append((fx, fy, fw, fh))
            try:
                probe.unlink()
            except OSError:
                pass
        except Exception as exc:
            log.info("  anchors: face detection unavailable (%s) — geometric fallback", exc)
        out: dict[str, Any] = {}
        for name in ("top", "bottom"):
            pts = found[name]
            if pts:
                med = lambda k: sorted(p[k] for p in pts)[len(pts) // 2]  # noqa: E731
                rule = "largest face" if (tile_map or {}).get("boyd") == name else "lectern face (middle of 3+, left of 2), edges excluded"
                out[name] = layout.Anchor(med(0), med(1), med(2), med(3), f"yunet faces, {rule}, median of {len(pts)} frame(s)", len(pts))
            else:
                out[name] = layout.Anchor(0.5, 0.42, None, None, "geometric fallback (no face detected)", 0)
            log.info("  anchors: %s tile -> fx=%.3f fy=%.3f (%s)", name, out[name].fx, out[name].fy, out[name].source)
        return out

    def _plan_cta(self, source: Path, offset: float, plan: Any, comp: dict[str, Any], cap_cfg: dict[str, Any],
                  sh_cfg: dict[str, Any], w_px: int, review_dir: Path) -> Any:
        """Where and when the "FULL VIDEO" call to action goes (cta.plan_cta):
        lower-left or lower-right of the bottom slot, whichever the measured
        face, the caption rail, the watermark, YouTube's UI and the sampled
        picture leave clearest; end-anchored by default. None when disabled."""
        from . import layout
        cta_cfg = sh_cfg.get("cta")
        if not cta.enabled(cta_cfg):
            return None
        wm = self._watermark_size(sh_cfg, w_px)
        wm_box = layout.watermark_box(sh_cfg, *wm) if wm else None
        cap_box = layout.caption_box(cap_cfg, sh_cfg)
        fps = int(sh_cfg.get("fps", 30))
        # a dry plan for the timing, then the picture under that window
        dry = cta.plan_cta(cta_cfg, plan.duration_s, comp, cap_box, wm_box, None, fps)
        times = [dry.start_s, (dry.start_s + dry.end_s) / 2.0, max(dry.start_s, dry.end_s - 0.1)]
        frames = []
        try:
            frames = cta.sample_canvas_frames(source, offset, plan.segments, comp, times, review_dir)
        except Exception as exc:
            log.info("  cta: frame sampling unavailable (%s) — geometry only", exc)
        place = cta.plan_cta(cta_cfg, plan.duration_s, comp, cap_box, wm_box, frames, fps)
        log.info("  cta: %s (scores left %.1f / right %.1f%s); text box %s; %.2f-%.2fs",
                 place.side, place.scores["left"]["score"], place.scores["right"]["score"],
                 "; " + "; ".join(place.notes) if place.notes else "",
                 (round(place.text_box.x), round(place.text_box.y), round(place.text_box.w), round(place.text_box.h)),
                 place.start_s, place.end_s)
        return place

    def _watermark_size(self, sh_cfg: dict[str, Any], w_px: int) -> tuple[float, float] | None:
        """The rendered watermark's size (width = watermark_width_frac of the
        canvas, height from the image), for the overlay layout. None when
        no watermark is configured."""
        raw = sh_cfg.get("watermark", render.DEFAULT_WATERMARK)
        if not raw:
            return None
        width = round(w_px * float(sh_cfg.get("watermark_width_frac", 0.11)))
        try:
            from PIL import Image
            with Image.open(str(raw)) as im:
                iw, ih = im.size
            return (float(width), float(width) * ih / max(1, iw))
        except Exception:
            return (float(width), float(width) * 0.6)

    def _caption_provider(self, cap_cfg: dict[str, Any]):
        """The phrase planner provider named in captions.rail.planner, if one
        is registered; deterministic otherwise. Providers propose indices,
        never text (captions.plan_phrases validates them)."""
        from . import captions
        name = str(cap_cfg.get("planner", "deterministic")).lower()
        if name in ("", "deterministic", "none"):
            return None
        provider = captions.PROVIDERS.get(name)
        if provider is None:
            log.warning("  captions: planner provider %r is not registered — deterministic", name)
        return provider

    def _judge_tile_map(self, source: Path, offset: float, case: dict[str, Any],
                        tiles: tuple[str, str], sh_cfg: dict[str, Any],
                        review_dir: Path) -> dict[str, Any]:
        """Which stacked tile is Judge Boyd's. The left source tile is stacked
        on TOP (see render_short duo_fill). `output.short.judge_tile`:
        auto -> recognise her with tools/identity.py on a frame from the
        case's own span; left/right -> forced. Falls back to
        judge_tile_default, and says so — a guessed map is recorded as
        unverified rather than presented as a measurement."""
        pref = str(sh_cfg.get("judge_tile", "auto")).lower()

        def mapping(boyd_tile: str, source_note: str) -> dict[str, Any]:
            return {"boyd": boyd_tile, "defendant": "bottom" if boyd_tile == "top" else "top",
                    "source": source_note}

        if pref in ("left", "right"):
            return mapping("top" if pref == "left" else "bottom", f"config judge_tile={pref}")
        try:
            import sys as _sys
            tools = Path(__file__).resolve().parents[2] / "tools"
            if str(tools) not in _sys.path:
                _sys.path.insert(0, str(tools))
            import cv2  # noqa: WPS433
            import identity  # noqa: WPS433
            at = (case.get("editorial") or {}).get("money_moment_s")
            if not isinstance(at, (int, float)):
                at = (float(case["start_s"]) + float(case["end_s"])) / 2.0
            frame = render.extract_thumbnail(source, max(0.0, float(at) - offset), review_dir / "tile_probe.jpg")
            bgr = cv2.imread(str(frame))
            row, score = identity.find_judge(bgr)
            if row is not None and score >= identity.COSINE_SAME:
                cx = float(row[0]) + float(row[2]) / 2.0
                lw, _lh, lx, _ly = (int(v) for v in tiles[0].split("=")[1].split(":"))
                return mapping("top" if cx < lx + lw else "bottom", f"identity (cosine {score:.2f})")
            log.info("  framing: Boyd not recognised in the probe frame (best cosine %.2f)", score)
        except Exception as exc:
            log.info("  framing: identity check unavailable (%s)", exc)
        default = str(sh_cfg.get("judge_tile_default", "right")).lower()
        return mapping("top" if default == "left" else "bottom",
                       f"default judge_tile_default={default} (unverified)")

    def _master_short_audio(self, sh_path: Path, sh_cfg: dict[str, Any]) -> dict[str, Any] | None:
        """Loudness-normalise the rendered short in place with the manual
        chain's masterer (tools/master_audio.py, -14 LUFS / -1.5 dBTP,
        video stream copied). The un-mastered render is kept beside it as
        short_raw.mp4. Any failure ships the render as it is, and says so."""
        if not sh_cfg.get("master_audio", True):
            return None
        try:
            import sys as _sys
            tools = Path(__file__).resolve().parents[2] / "tools"
            if str(tools) not in _sys.path:
                _sys.path.insert(0, str(tools))
            import master_audio  # noqa: WPS433
            dst = sh_path.with_name("short_mastered.mp4")
            before, after, _meas = master_audio.master(str(sh_path), str(dst))
            raw = sh_path.with_name("short_raw.mp4")
            if raw.exists():
                raw.unlink()
            sh_path.replace(raw)
            dst.replace(sh_path)
            log.info("  audio: mastered %.1f -> %.1f LUFS, true peak %.1f dBTP",
                     before[0], after[0], after[2])
            return {"before_lufs": before[0], "after_lufs": after[0], "true_peak_dbtp": after[2],
                    "duration_s": render.probe_duration(sh_path)}
        except Exception as exc:
            log.warning("  audio: loudness mastering unavailable (%s) — shipping the render as is", exc)
            return {"error": str(exc)}

    def _short_render_qc(self, sh_path: Path, sh_duration: float, plan: Any,
                         sh_cfg: dict[str, Any]) -> list[dict[str, Any]]:
        """The file must match the plan: duration, ceiling, canvas, audio."""
        gates: list[dict[str, Any]] = []

        def gate(name: str, ok: bool, detail: str) -> None:
            gates.append({"gate": name, "ok": bool(ok), "detail": detail})

        gate("file_exists", sh_path.exists() and sh_path.stat().st_size > 0, str(sh_path))
        gate("duration_matches_plan", abs(float(sh_duration) - float(plan.duration_s)) <= 0.6,
             f"rendered {sh_duration:.2f}s vs planned {plan.duration_s:.2f}s")
        ceiling = float(sh_cfg.get("max_duration_s", 59))
        gate("under_ceiling", float(sh_duration) <= ceiling + 0.05, f"{sh_duration:.2f}s <= {ceiling:.0f}s")
        try:
            w, h = render.probe_dimensions(sh_path)
            want = list(sh_cfg.get("resolution", [1080, 1920]))
            gate("canvas", [w, h] == want, f"{w}x{h} (want {want[0]}x{want[1]})")
        except Exception as exc:
            gate("canvas", False, f"probe failed: {exc}")
        try:
            gate("audio_present", render._has_audio(sh_path), "audio stream present")
        except Exception as exc:
            gate("audio_present", False, f"probe failed: {exc}")
        return gates

    # -------------------------------------------------------- short: legacy

    def _short_legacy(self, source: Path, offset: float, case: dict[str, Any], case_key: str,
                      pkg: dict[str, Any], review_dir: Path, sh_cfg: dict[str, Any],
                      crop: str | None, bg_crop: str | None, transcript: Any,
                      result: dict[str, Any]) -> None:
        """The pre-SHORTS_EDITOR_V2 short: the model's beats through
        plan_short_segments, static duo_fill, grouped captions. Kept verbatim
        for rollback via `output.short.editor: legacy`."""
        segments = render.plan_short_segments(case, sh_cfg)
        if not case.get("shortable") or segments is None:
            # Don't print shortable_reasoning when the model said the case IS
            # shortable — that text argues the opposite of what happened and
            # hides which check actually failed.
            why = (
                case.get("shortable_reasoning") or "model marked it unshortable"
                if not case.get("shortable")
                else "beat plan rejected by plan_short_segments (order, "
                     "case bounds, or duration budget)"
            )
            log.info("  render: no short — %s", why)
            return

        log.info("  render: short (%d beats, %.1fs)", len(segments),
                 sum(s.duration for s in segments))

        # THE THOMPSON LOOK (short_v3): full-bleed duo, no black anywhere.
        #
        # Each tile is cropped to the exact aspect of the half-canvas it fills
        # (1080x960 = 1.125:1) and centred on its subject, rather than being
        # letterboxed into the slot. render_short has had a `duo_fill` mode and
        # a `tile_crops` argument since that build; the daily path never
        # selected it, so every automated short came out as split_stack — the
        # tiles floating on a blurred backdrop with black above and below,
        # which is the thing Nathan asked to get rid of.
        #
        # Falls back to the old behaviour when the two tiles cannot be measured
        # (a Zoom grid, a screen-share): a duo_fill built from a bad rectangle
        # is worse than a letterbox.
        sh_cfg = dict(sh_cfg)
        tile_windows = None
        tiles = render.detect_tile_crops(source)
        if tiles:
            w_px, h_px = sh_cfg.get("resolution", [1080, 1920])
            slot_aspect = w_px / (h_px / 2)
            focus = sh_cfg.get("tile_focus", [0.5, 0.5])
            zoom = float(sh_cfg.get("tile_zoom", 1.0))
            tile_windows = (
                render.plan_fill_window(tiles[0], slot_aspect, tuple(focus), zoom),
                render.plan_fill_window(tiles[1], slot_aspect, tuple(focus), zoom),
            )
            sh_cfg["vertical_mode"] = "duo_fill"
            log.info("  framing: duo_fill — %s | %s (slot aspect %.3f)",
                     tile_windows[0], tile_windows[1], slot_aspect)
        else:
            log.info("  framing: tiles not measurable — falling back from duo_fill")

        # choose_vertical_layout honours an explicit vertical_mode, so the
        # margin always matches the layout render_short will actually build.
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
            # Speaker-anchored captions: the text sits beside whoever is
            # talking, which is the last piece of the approved Thompson short.
            # v3 hand-wrote the turns for four beats; diarize.py derives them.
            turns = None
            if cap_cfg.get("slot_margins"):
                try:
                    raw = diarize.diarize(source)
                    if raw:
                        # diarize works in the downloaded file's timeline;
                        # segments and map_words_to_timeline are in SOURCE
                        # time, so shift before mapping or every turn lands
                        # `offset` seconds early.
                        mapped = render.map_words_to_timeline(
                            [Word(t=t + offset, w=who) for t, who in raw], segments
                        )
                        if mapped:
                            turns = [(0.0, mapped[0].w)] + [
                                (m.t, m.w) for m in mapped[1:]
                            ]
                            log.info("  captions: %d speaker turns anchored", len(turns))
                except Exception as exc:
                    # A caption in the wrong slot is cosmetic; losing the short
                    # is not. Fall back to a single margin.
                    log.warning("  captions: diarisation unavailable (%s)", exc)

            ass_path = render.build_ass(
                words, 0.0, elapsed, cap_cfg,
                self.cfg.get("packaging.short.end_card"),
                review_dir / "captions.ass",
                turns=turns,
            )

        sh_path = review_dir / "short.mp4"
        sh_duration = render.render_short(
            source, offset, segments, sh_cfg, ass_path, sh_path,
            crop=crop, bg_crop=bg_crop, tile_crops=tile_windows,
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
            "vertical_thumbnail_required": True,
            "vertical_thumbnail": None,
        }
        result["short"]["vertical_thumbnail"] = self._produce_short_vertical_thumbnail(
            sh_path, case.get("approved_vertical_thumbnail"), review_dir
        )

    def _render_approved_narrated_intro(self, source: Path, offset: float, directive: Any,
                                        review_dir: Path, sh_cfg: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        """Render an already approved local intro spec; never acquire media."""
        directive = dict(directive or {})
        required = {"voice_path", "text", "shots", "caption_cues"}
        missing = sorted(required - set(directive))
        if missing:
            raise ValueError(f"approved narrated intro missing {missing}")
        source_hooks: list[narrated_short_intro.SourceHookSpec] = []
        for row in directive.get("source_hooks") or []:
            row = dict(row)
            hook_path = Path(row.pop("path"))
            if not hook_path.is_absolute():
                hook_path = self.cfg.root / hook_path
            source_hooks.append(narrated_short_intro.SourceHookSpec(path=hook_path, **row))
        narrated_short_intro.validate_source_hooks(tuple(source_hooks))
        voice = Path(directive["voice_path"])
        if not voice.is_absolute():
            voice = self.cfg.root / voice
        freeze_circle = None
        if directive.get("freeze_circle"):
            freeze_row = dict(directive["freeze_circle"])
            ding_path = Path(freeze_row.pop("ding_path"))
            if not ding_path.is_absolute():
                ding_path = self.cfg.root / ding_path
            freeze_circle = narrated_short_intro.FreezeCircleCue(
                ding_path=ding_path,
                circle_box=tuple(freeze_row.pop("circle_box")),
                **freeze_row,
            )
        transition_sfx = None
        if directive.get("transition_sfx_path"):
            transition_sfx = Path(directive["transition_sfx_path"])
            if not transition_sfx.is_absolute():
                transition_sfx = self.cfg.root / transition_sfx
        spec = narrated_short_intro.NarratedIntroSpec(
            voice_path=voice, text=str(directive["text"]),
            shots=tuple(narrated_short_intro.Shot(**row) for row in directive["shots"]),
            caption_cues=tuple(tuple(row) for row in directive["caption_cues"]),
            narrator_label=str(directive.get("narrator_label") or ""),
            freeze_circle=freeze_circle,
            transition_sfx_path=transition_sfx,
            transition_sfx_gain_db=float(directive.get("transition_sfx_gain_db", -24.0)),
        )
        target = review_dir / "approved_narrated_intro.mp4"
        evidence = review_dir / "approved_narrated_intro.json"
        record = narrated_short_intro.render_moving_broll(source, offset, spec, target, sh_cfg, evidence)
        record["voice_sha256"] = readiness.sha256_file(voice)
        record["source_hooks"] = []
        for index, hook in enumerate(source_hooks):
            normalized = review_dir / f"approved_source_hook_{index + 1}_48k.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(hook.path), "-c:v", "copy",
                            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
                            str(normalized)], check=True)
            record["source_hooks"].append({
                "path": str(hook.path.resolve()), "normalized_path": str(normalized.resolve()),
                "sha256": hook.sha256, "source_start_s": hook.source_start_s,
                "source_end_s": hook.source_end_s, "text": hook.text, "speaker": hook.speaker,
                "duration_s": render.probe_duration(normalized),
            })
        evidence.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return target, record

    def _produce_short_vertical_thumbnail(self, short_path: Path, directive: Any,
                                          review_dir: Path) -> dict[str, Any] | None:
        """Consume an explicit configured-brain-approved local recipe; never spend credits."""
        if not directive:
            return None
        directive = validate_vertical_directive(
            directive, str(self.cfg.require("packaging.thumbnail.direct.model"))
        )
        frames = review_dir / "short_thumbnail_frames"
        frames.mkdir(parents=True, exist_ok=True)
        top_t, bottom_t = float(directive["top_output_s"]), float(directive["bottom_output_s"])
        top = render.extract_thumbnail(short_path, top_t, frames / "top.jpg")
        bottom = render.extract_thumbnail(short_path, bottom_t, frames / "bottom.jpg")
        record = short_thumbnail.build(top, bottom, str(directive["hook_text"]),
                                       review_dir / "short_thumbnail_vertical.jpg", short_path=short_path,
                                       top_crop=tuple(directive["top_crop"]), bottom_crop=tuple(directive["bottom_crop"]),
                                       direction_model=str(directive["direction_model"]))
        record["source_timecodes"] = {"top_output_s": top_t, "bottom_output_s": bottom_t}
        Path(record["file_path"]).with_suffix(".json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record

    def _repeat_tiebreak(self, video_id: str, eligible: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Re-order ELIGIBLE candidates so a repeat defendant wins only inside
        analysis.repeat_defendant.tie_break_window points (editorial.tiebreak_order).

        Repeat = the defendant already has scored hearings in >= min_dockets
        distinct dockets in the store (repeats.find_episodes), which includes
        the docket being scored because analyze_docket saved its rows first.
        Any failure here leaves the order untouched — ranking must never break
        a run.
        """
        rc = dict(self.cfg.get("analysis.repeat_defendant", {}) or {})
        if not rc.get("enabled", False) or len(eligible) < 2:
            return eligible
        try:
            from . import editorial, repeats
            min_dockets = int(rc.get("min_dockets", 2))
            window = float(rc.get("tie_break_window", editorial.REPEAT_TIE_WINDOW))
            repeat_keys = {
                h["case_key"]
                for ep in repeats.find_episodes(self.store.conn)
                if ep.dockets >= min_dockets
                for h in ep.hearings
            }
            def is_repeat(c: dict[str, Any]) -> bool:
                return self.store.case_key(video_id, c["start_s"]) in repeat_keys
            for c in eligible:
                if is_repeat(c):
                    c["repeat_defendant"] = True     # package_post may say "back in court"
            ordered = editorial.tiebreak_order(eligible, is_repeat, window)
            if [c["start_s"] for c in ordered] != [c["start_s"] for c in eligible]:
                log.info("  repeat-defendant tie-break (window %.0f) re-ordered the picks: %s",
                         window, ", ".join(f"{c.get('defendant_name','?')} {c['total_score']:g}"
                                            + (" (repeat)" if is_repeat(c) else "") for c in ordered))
            return ordered
        except Exception as exc:
            log.warning("  repeat tie-break skipped: %s", exc)
            return eligible

    def _story_memory(self, docket: discover.Docket, case: dict[str, Any]) -> dict[str, Any]:
        """Print the pre-flight memory block and refuse a story already on record.

        Runs before any download, model call or render. Raises StoryReuseError
        when the ledger holds work for this story and no revisit reason was
        given; with a reason, the reopening is recorded against the story so the
        next reader knows it was deliberate.
        """
        ledger = StoryLedger(self.store.conn)
        memory = ledger.preflight(
            docket.video_id, float(case["start_s"]), float(case["end_s"]),
            case.get("cause_number"), case.get("defendant_name"))
        for line in ledger.format_preflight(memory).splitlines():
            log.info("%s", line)
        if memory["story_match"] != "NEW" and not memory["selection_eligible"]:
            revisit = getattr(self, "_revisit_reason", None)
            if not revisit:
                raise StoryReuseError(
                    f"the ledger already holds work for this story "
                    f"({memory['story_id']}) — {memory['reason']}. If this story is "
                    'genuinely being reopened, re-run with --revisit-reason "<why>".')
            ledger.add_decision(
                memory["story_id"], "REVISIT_AUTHORISED", reason=revisit,
                source="operator (boyd run --case --revisit-reason)", quote=revisit)
            log.warning("  story memory: reopening %s — %s", memory["story_id"], revisit)
        return memory

    def _produce_thumbnail(self, source: Path, offset: float, case: dict[str, Any],
                           pkg: dict[str, Any], review_dir: Path) -> dict[str, str]:
        """Build a fresh image; never accept an old file after a failed rebuild."""
        hook_at = max(0.0, case["hook_start_s"] - offset)
        white, yellow = split_thumbnail_quote(pkg)
        target = review_dir / "thumbnail_quote.jpg"
        tcfg = dict(self.cfg.get("packaging.thumbnail", {}) or {})
        # 2026-09-19: this ran only under `direct_gen`, so the configured
        # `legacy` compositor — which renders pkg["thumbnail_quote"] onto the
        # finished image — spent the render with no review of its words at all.
        # The review is now a precondition of BOTH builders: it is one cached
        # call, it happens before any image exists, and a refusal here stops
        # the case instead of shipping a bland factual label.
        if pkg.get("producer_brain"):
            from . import thumbnail_copy
            worker = self.analyzer
            reserved = int(getattr(worker, "reserved_calls", 0))
            worker.reserved_calls = reserved + int(getattr(self, "_thumbnail_model_calls_used", 0))
            # The copy review judges titles and thumbnail wording against the
            # packaging rules; it runs through the same analyzer, so the loader
            # supplies the current context to that one call and nothing else.
            previous_loader = getattr(worker, "stage_context_loader", None)
            worker.stage_context_loader = stage_context.load_context
            try:
                thumbnail_copy.ensure_review(worker, pkg, review_dir / "thumbnail_copy_review.json")
            finally:
                worker.reserved_calls = reserved
                worker.stage_context_loader = previous_loader
        experiment = pkg.get("thumbnail_experiment") or {}
        if experiment.get("type") == "thumbnail_text_only":
            # An operator-supplied, source-reviewed common base is required.
            # This branch cannot silently create a base or switch image providers.
            from .thumbnail_text_test import build_text_only_experiment, validate_experiment, Typography
            if not pkg.get("producer_brain"):
                raise RuntimeError("text-only experiment requires source-grounded packaging")
            base = Path(str(experiment.get("base_path") or ""))
            if not base.is_file() or readiness.sha256_file(base) != experiment.get("base_sha256"):
                raise RuntimeError("text-only common base is missing or changed")
            pairs = pkg.get("packaging_pairs") or []
            title = str(experiment.get("fixed_title") or "")
            if not title or any(pair.get("title") != title for pair in pairs):
                raise RuntimeError("text-only experiment must keep every video title fixed")
            receipt = build_text_only_experiment(
                base=base, title=title,
                variants=[{"label": p["label"], "text": p["thumbnail_text"],
                           "emphasis": p["thumbnail_yellow"]} for p in pairs],
                evidence=json.dumps(thumbnail_copy.review_input(pkg), ensure_ascii=False),
                outdir=review_dir / "text_test",
                rectangle=experiment.get("text_rectangle"),
                typography=Typography(**(experiment.get("typography") or {})),
            )
            manifest = review_dir / "text_test" / "thumbnail-text-only.json"
            validation = validate_experiment(manifest)
            if not validation["ok"]:
                raise RuntimeError(f"text-only thumbnail validation failed: {validation['failures']}")
            paths = {v["label"]: v["png_path"] for v in receipt["variants"]}
            for path in paths.values():
                require_thumbnail(Path(path))
            return {"mode": "thumbnail_text_only", "complete": True,
                    "model": self.cfg.get("packaging.thumbnail.direct.model"),
                    "file_path": paths["A"], "candidates": paths,
                    "manifest": str(manifest), "status": "candidate", "review": "required",
                    "images_generated_total": 0, "model_calls_used": 0}
        cache_path = review_dir / "thumbnail_cache.json"
        cache_key = {
            "source_sha256": readiness.sha256_file(source), "offset_s": offset,
            "case_start_s": case["start_s"], "hook_start_s": case["hook_start_s"],
            "packaging_pairs": pkg.get("packaging_pairs"),
        } if tcfg.get("mode") == "direct_gen" else None
        if tcfg.get("mode") == "direct_gen" and cache_path.is_file():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("key") == cache_key:
                candidate = cached.get("output") or {}
                paths = candidate.get("candidates") or {}
                hashes = cached.get("hashes") or {}
                if (candidate.get("complete") is True and set(paths) == set(hashes) == {"A", "B", "C"}
                        and all(readiness.sha256_file(Path(paths[k])) == hashes[k] for k in paths)):
                    for path in paths.values():
                        require_thumbnail(Path(path))
                    if pkg.get("producer_brain"):
                        thumbnail_copy.require_rendered_copy(pkg, candidate)
                    log.info("  thumbnail: reusing three unchanged hash-verified candidates")
                    return candidate
        dcfg = dict(tcfg.get("direct") or {})
        dcfg["budget"] = min(
            int(dcfg.get("budget", 9)),
            int(getattr(
                self,
                "_thumbnail_images_remaining",
                self.cfg.get("output.max_thumbnail_images_per_run", 9),
            )),
        )
        model_limit = int(self.cfg.get("analysis.max_model_calls_per_run", 20))
        analysis_worker = getattr(self, "_analyzer", None)
        analysis_calls = int(getattr(analysis_worker, "calls_used", 0)) if analysis_worker else 0
        dcfg["model_call_budget"] = max(
            0,
            model_limit
            - analysis_calls
            - int(getattr(self, "_thumbnail_model_calls_used", 0)),
        )
        tcfg["direct"] = dcfg

        def legacy() -> dict[str, str]:
            # Same filesystem permits atomic replacement and preserves the last
            # usable image when a builder crashes or writes an invalid result.
            with tempfile.TemporaryDirectory(prefix="thumbnail-", dir=review_dir) as stage:
                staged = Path(stage) / target.name
                thumbnail.build(source, hook_at, white, yellow, staged, tcfg)
                require_thumbnail(staged)
                # Which construction shipped, and why: the builder records it
                # beside the image (Q3 cut-out vs the single-plate fallback) so
                # the manifest carries the answer instead of a log line.
                construction = staged.with_name(staged.name + ".construction.json")
                record = {}
                if construction.is_file():
                    try:
                        record = json.loads(construction.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        record = {}
                staged.replace(target)
                if record:
                    # The staging dir dies with the block; keep the same record
                    # beside the shipped image for the reviewer.
                    target.with_name(target.name + ".construction.json").write_text(
                        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
            log.info("  thumbnail: validated candidate -> %s", target.name)
            return {"file_path": str(target), "status": "candidate", "review": "required",
                    **record}

        def direct() -> dict[str, Any] | None:
            # thumbnail.mode: direct_gen (2026-09-06) - three generated concepts,
            # the A control is the file_path; all three are candidates for the test
            res = thumbnail.build_direct(source, offset, case, pkg, review_dir, tcfg)
            if res:
                used = int(res.get("images_generated_total") or 0)
                self._thumbnail_model_calls_used = int(
                    getattr(self, "_thumbnail_model_calls_used", 0)
                ) + int(res.get("model_calls_used") or 0)
                self._thumbnail_images_remaining = max(
                    0,
                    int(getattr(self, "_thumbnail_images_remaining", dcfg["budget"])) - used,
                )
                if res.get("file_path"):
                    require_thumbnail(Path(res["file_path"]))
                log.info(
                    "  thumbnail: direct_gen %s candidates -> %s (%d image(s), %d Sol call(s) remain this run)",
                    "complete" if res.get("complete") else "incomplete",
                    ", ".join(Path(p).name for p in res.get("candidates", {}).values()) or "none",
                    self._thumbnail_images_remaining,
                    max(0, model_limit - analysis_calls - self._thumbnail_model_calls_used),
                )
            return res

        output = thumbnail.build_for_mode(tcfg, direct, legacy)
        if output.get("mode") == "direct_gen" and output.get("complete") is True and pkg.get("producer_brain"):
            thumbnail_copy.require_rendered_copy(pkg, output)
        if output.get("mode") == "direct_gen" and output.get("complete") is True:
            candidates = output.get("candidates") or {}
            if set(candidates) == {"A", "B", "C"}:
                cache_path.write_text(json.dumps({
                    "key": cache_key, "output": output,
                    "hashes": {k: readiness.sha256_file(Path(v)) for k, v in candidates.items()},
                }, ensure_ascii=False, indent=2), encoding="utf-8")
        if tcfg.get("mode") == "direct_gen" and output.get("mode") != "direct_gen":
            # A direct session failed before it could report usage. Consume the
            # remaining allowance conservatively so another case cannot start
            # an unbounded second image session in the same run.
            self._thumbnail_images_remaining = 0
            # The failed subprocess may have called Sol before losing its
            # structured result. Consume the remaining call allowance rather
            # than guess low and permit another case to exceed the ceiling.
            self._thumbnail_model_calls_used = max(
                int(getattr(self, "_thumbnail_model_calls_used", 0)),
                model_limit - analysis_calls,
            )
        return output

    def _bank_candidates(
        self,
        per_day: int,
        excluded: set[str],
    ) -> list[tuple[discover.Docket, dict[str, Any], str, int]]:
        rows: list[tuple[discover.Docket, dict[str, Any], str, int]] = []
        for raw_row in self.store.banked_cases(max(20, per_day * 5)):
            raw = dict(raw_row)
            try:
                case = json.loads(raw.get("payload") or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            video_id = str(raw.get("video_id") or case.get("video_id") or "")
            docket_row = self.store.get_docket_row(video_id)
            if not video_id or docket_row is None:
                continue
            key = self.store.case_key(video_id, float(case.get("start_s", raw.get("start_s", 0))))
            if key in excluded or self.store.case_published(key):
                continue
            excluded.add(key)
            stored = dict(docket_row)
            docket = discover.Docket(
                video_id=video_id,
                title=str(stored.get("title") or video_id),
                duration_s=float(stored.get("duration_s") or 0.0),
                docket_date=str(stored.get("docket_date") or ""),
                session=discover.parse_session(str(stored.get("title") or "")),
            )
            case.setdefault("eligible", True)
            case.setdefault("total_score", float(raw.get("total_score") or 0.0))
            case.setdefault("summary", "stored eligible case")
            rows.append((docket, case, "bank", len(rows)))
        return rows

    def _attach_competitor_matches(
        self,
        candidates: list[tuple[discover.Docket, dict[str, Any], str, int]],
        lead_transcripts: list[tuple[competitor.Lead, Any]],
    ) -> None:
        if not lead_transcripts:
            return

        threshold = float(self.cfg.get("competitor.min_transcript_overlap", 0.08))
        transcript_cache: dict[str, Any] = {}
        for docket, case, _source, _order in candidates:
            try:
                transcript = transcript_cache.get(docket.video_id)
                if transcript is None:
                    transcript = get_transcript(
                        docket.video_id,
                        self.work / docket.video_id,
                        source="auto_captions",
                        whisper_fallback=False,
                    )
                    transcript_cache[docket.video_id] = transcript
                windows = case.get("story_windows") or self.store.case_windows(
                    docket.video_id, case["start_s"],
                ) or [[case["start_s"], case["end_s"]]]
                case_text = " ".join(
                    transcript.text_between(float(window[0]), float(window[1]))
                    for window in windows
                )
                match = competitor.best_match(case_text, lead_transcripts, min_overlap=threshold)
            except Exception as exc:
                log.warning("  competitor match skipped for %s: %s", docket.video_id, exc)
                continue
            if not match:
                continue
            case["competitor_lead"] = match
            self.store.save_case(docket.video_id, case, case.get("rank"))
            log.info(
                "  competitor lead resolved: %s <- %s (overlap %.1f%%, %.0f views/day)",
                self.store.case_key(docket.video_id, case["start_s"]),
                match["channel"],
                100 * match["transcript_overlap"],
                match["views_per_day"],
            )

    def _write_daily_record(
        self,
        candidates: list[tuple[discover.Docket, dict[str, Any], str, int]],
        produced: list[dict[str, Any]],
        failures: list[str],
        status: str,
    ) -> Path:
        log_dir = self.cfg.path("paths.logs") / "daily-runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "created_at": _now(),
            "status": status,
            "limits": {
                "pairs": int(self.cfg.get("output.clips_per_day", 1)),
                "sol_calls": int(self.cfg.get("analysis.max_model_calls_per_run", 20)),
                "thumbnail_images": int(self.cfg.get("output.max_thumbnail_images_per_run", 9)),
                "cli_attempts": int(self.cfg.get("analysis.cli_attempts", 1)),
            },
            "candidates": [
                {
                    "case_key": self.store.case_key(docket.video_id, case["start_s"]),
                    "source_pool": source,
                    "score": case.get("total_score"),
                    "summary": case.get("summary"),
                    "competitor_lead": case.get("competitor_lead"),
                }
                for docket, case, source, _order in candidates
            ],
            "produced": [
                {"case_key": row.get("case_key"), "review_dir": row.get("review_dir")}
                for row in produced
            ],
            "failures": list(failures),
            "usage": {
                "model_calls": list(getattr(self._analyzer, "usage_events", [])) if self._analyzer else [],
                "thumbnail_model_calls": int(getattr(self, "_thumbnail_model_calls_used", 0)),
                "sol_calls_total": (
                    int(getattr(self._analyzer, "calls_used", 0)) if self._analyzer else 0
                ) + int(getattr(self, "_thumbnail_model_calls_used", 0)),
                "thumbnail_images_reported": (
                    int(self.cfg.get("output.max_thumbnail_images_per_run", 9))
                    - int(getattr(self, "_thumbnail_images_remaining", self.cfg.get("output.max_thumbnail_images_per_run", 9)))
                ),
                "token_usage": None,
                "estimated_cost": None,
            },
        }
        path = log_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000:06d}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    # ------------------------------------------------------------------ driver

    def run_case(self, case_key: str, dry_run: bool = False,
                 revisit_reason: str | None = None) -> dict[str, Any] | None:
        """Render one specific already-scored case, chosen by the operator.

        run_daily() picks the top scorer; this renders whoever you name. The
        case must already exist in the store — this deliberately does not
        re-analyse, so an operator cannot use it to bypass the safety gate on
        a case that was never scored.

        `revisit_reason` is how an operator reopens a story that the ledger says
        already has a package. The reason is recorded against the story; a bare
        case key is not enough, because a new key is exactly what a re-scored
        hearing looks like.
        """
        self._revisit_reason = revisit_reason
        case = self.store.get_case(case_key)
        if case is None:
            log.error("unknown case %s — run `boyd bank` to list available cases", case_key)
            return None

        if self.store.case_published(case_key):
            log.error("case %s is already published", case_key)
            return None

        row = self.store.get_docket_row(case_key.split(":")[0])
        if row is None:
            log.error("no stored docket for %s", case_key)
            return None

        docket = discover.Docket(
            video_id=row["video_id"],
            title=row["title"],
            duration_s=row["duration_s"] or 0.0,
            docket_date=row["docket_date"] or "",
            session="unknown",
        )

        if dry_run:
            log.info(
                "  [dry-run] stored candidate %s score %.1f — would render: %s",
                case_key,
                case.get("total_score") or 0.0,
                (case.get("summary") or "")[:100],
            )
            return None

        # BOYD_EDITORIAL_V2 stabilisation: a row scored under another rubric
        # version is stale. It is re-scored under the current prompt — safety
        # gate and all, on the full docket transcript — and must clear the
        # current gates before it can be rendered. This is not a bypass: the
        # case still has to have been segmented and scored, and the safety
        # gate runs again.
        rubric_version = analyze.current_rubric_version()
        if case.get(analyze.RUBRIC_VERSION_KEY) != rubric_version:
            log.warning("case %s was scored under %r; re-scoring under %r before render",
                        case_key, case.get(analyze.RUBRIC_VERSION_KEY), rubric_version)
            work = self.work / docket.video_id
            work.mkdir(parents=True, exist_ok=True)
            transcript = get_transcript(
                docket.video_id, work,
                source=self.cfg.get("transcription.source", "auto_captions"),
                language=self.cfg.get("transcription.language", "en"),
                whisper_fallback=self.cfg.get("transcription.whisper_fallback", True),
                whisper_model=self.cfg.get("transcription.whisper_model", "medium"),
            )
            meta = _docket_meta(docket)
            rescored = self.analyzer.score(transcript, [analyze.stage1_view(case)], meta, full_context=True)
            if not rescored:
                log.error("case %s: re-score returned nothing — refusing to render", case_key)
                return None
            case = rescored[0]
            self.store.save_case(docket.video_id, case, case.get("rank"))
            if not case["eligible"]:
                log.error("case %s does not clear the current gates: %s — refusing to render",
                          case_key, case["ineligible_reason"])
                return None

        # A row scored under the CURRENT rubric can still be HOLD/SKIP (an
        # operator-bounded re-score, 2026-09-06: Miosek 71 = HOLD). The
        # re-score branch above checks eligibility; this one applies the same
        # gate to rows that arrive already current.
        if not case.get("eligible", True):
            log.error("case %s is not eligible under the current rubric: %s — refusing to render",
                      case_key, case.get("ineligible_reason"))
            return None

        safety = case.get("safety", {})
        if not safety.get("safety_pass"):
            rules = ", ".join(safety.get("safety_rule_violations") or []) or "unspecified"
            log.error("case %s failed the safety gate (%s) — refusing to render", case_key, rules)
            return None

        log.info("case %s — %s (score %.1f)", case_key,
                 case.get("defendant_name") or "?", case.get("total_score") or 0.0)

        try:
            result = self.produce(docket, case)
        except StoryReuseError as exc:
            log.error("  %s", exc)
            return None
        log.info("  rendered -> %s", result["review_dir"])
        return result

    def run_moment(self, key: str, dry_run: bool = False) -> dict[str, Any] | None:
        """Render one judged MOMENT — the thing this channel actually sells.

        See claude/MOMENTS.md. The unit is the 30-60 seconds where Judge Boyd
        stops doing procedure and starts talking, not the hearing it sits in.

        No re-analysis happens here, exactly as in run_case(): the moment must
        already have been mined AND judged, so an operator cannot use this to
        bypass the judge's is_boyd / safe_to_publish verdicts.

        Unlike run_case() this does NOT require the docket to be in the store.
        Four of the five moments cut on 2026-08-18 came from dockets the case
        pipeline never scored — the archive holds 352 transcripts and the DB
        holds 44 dockets — so refusing unknown dockets would reject most of the
        catalogue. Metadata is probed on demand instead.
        """
        judged_path = self.cfg.root / "state" / "moments_judged.json"
        if not judged_path.exists():
            log.error("no state/moments_judged.json — run scripts/judge_moments.py first")
            return None
        judged = json.loads(judged_path.read_text(encoding="utf-8"))
        rec = judged.get(key)
        if rec is None:
            near = [k for k in judged if k.startswith(key.split(":")[0])]
            log.error("unknown moment %s%s", key,
                      f" — same docket has {near}" if near else "")
            return None

        try:
            case = momentrun.moment_to_case(rec)
        except momentrun.MomentError as exc:
            log.error("moment %s is not renderable: %s", key, exc)
            return None

        video_id = key.split(":")[0]
        if dry_run:
            log.info(
                "  [dry-run] stored judged moment %s — would render %.0f-%.0fs",
                key, case["start_s"], case["end_s"],
            )
            return None
        row = self.store.get_docket_row(video_id)
        if row is not None:
            docket = discover.Docket(
                video_id=row["video_id"], title=row["title"],
                duration_s=row["duration_s"] or 0.0,
                docket_date=row["docket_date"] or "", session="unknown")
        else:
            log.info("  docket %s is not in the store — probing metadata", video_id)
            meta = discover.probe(video_id)
            title = meta.get("title") or video_id
            docket = discover.Docket(
                video_id=video_id, title=title,
                duration_s=float(meta.get("duration") or 0.0),
                docket_date=discover.parse_docket_date(title),
                session=discover.parse_session(title))
            # Register it so the render's DB writes have a foreign key to land
            # on. INSERT OR IGNORE, so this is safe to repeat.
            self.store.add_docket(docket.video_id, docket.title,
                                  docket.docket_date, docket.duration_s)

        # clips.case_key is a foreign key to cases.case_key, so the moment has
        # to exist as a case row before produce() saves a clip against it.
        # Without this the whole render completes and then dies on
        # "FOREIGN KEY constraint failed" with the encode already paid for.
        self.store.save_case(docket.video_id, case, None)

        log.info("moment %s — out-of-pocket %s, %.0fs", key,
                 case.get("out_of_pocket"), case["end_s"] - case["start_s"])
        log.info('  hook: "%s"', (case.get("hook_quote") or "")[:110])

        result = self.produce(docket, case)
        log.info("  rendered -> %s", result["review_dir"])
        return result

    def run_daily(self, limit: int | None = None, dry_run: bool = False) -> list[dict[str, Any]]:
        # The tray switch suspends boyd-clips processes with NtSuspendProcess
        # rather than killing them. Left RED on 2026-08-14, it froze the next
        # run mid-download: a process that looked alive, a .part file that
        # never grew, and no error anywhere in the log. Nothing in the output
        # distinguished "suspended" from "slow", and it cost a day. Refuse to
        # start instead of starting something that cannot finish.
        paused = self.cfg.path("paths.state_db").parent / "paused.flag"
        if paused.exists():
            raise PausedError(
                f"{paused} is present — the tray switch is RED and this run would be "
                "suspended mid-download rather than fail. "
                "Resume with: powershell -File tools/boyd-toggle.ps1"
            )

        lead_transcripts: list[tuple[competitor.Lead, Any]] = []
        if self.cfg.get("competitor.enabled", False) and not dry_run:
            try:
                leads = competitor.list_recent(
                    self.cfg.get("competitor.channels", []),
                    per_channel=int(self.cfg.get("competitor.per_channel", 4)),
                    max_leads=int(self.cfg.get("competitor.max_leads_per_run", 6)),
                )
                lead_transcripts = competitor.load_transcripts(
                    leads, self.work / "competitor_leads",
                )
                log.info(
                    "competitor: %d bounded lead(s), %d with captions",
                    len(leads), len(lead_transcripts),
                )
            except Exception as exc:
                log.warning("competitor lead scan unavailable: %s", exc)

        new = [] if dry_run else self.discover()
        configured_daily_limit = max(1, int(self.cfg.get("output.clips_per_day", 1)))
        per_day = configured_daily_limit
        if limit is not None:
            # CLI limit may make a diagnostic run smaller; it cannot bypass the
            # configured daily production ceiling.
            per_day = min(configured_daily_limit, max(1, int(limit)))
        candidates: list[tuple[discover.Docket, dict[str, Any], str, int]] = []

        bundle_call_reserve = (
            int(bool(self.cfg.get("analysis.gates.recheck_selection", True)))
            + int(bool(self.cfg.get("analysis.producer_brain.enabled", True)))
            + int(self.cfg.get("packaging.thumbnail.mode") == "direct_gen")
        )
        if new:
            # Selection may use the rest of the Sol allowance, but it cannot
            # consume the minimum needed to turn a winner into a full bundle.
            self.analyzer.reserved_calls = bundle_call_reserve

        # Analyze every available docket before choosing anything. The previous
        # loop selected up to `clips_per_day` inside each docket, so limit=1
        # could render several cases and an older weak docket could win before
        # a stronger recent docket was even scored.
        self._revisit_reason = None
        ledger = StoryLedger(self.store.conn)
        for docket_index, docket in enumerate(new):
            log.info("docket %s — %s", docket.video_id, docket.title)
            try:
                scored = self.analyze_docket(docket)
            except analyze.ModelCallLimitError as exc:
                log.warning("  %s — selection scan stops; remaining dockets stay pending", exc)
                break
            except RefusalError as exc:
                log.error("  %s — skipping docket", exc)
                self.store.mark_docket(docket.video_id, "refused", str(exc))
                continue
            except Exception as exc:
                log.error("  analysis failed: %s", exc)
                log.debug(traceback.format_exc())
                self.store.mark_docket(docket.video_id, "error", str(exc))
                continue

            eligible = []
            for candidate in scored:
                if not candidate["eligible"]:
                    continue
                key = self.store.case_key(docket.video_id, candidate["start_s"])
                blocked, why = ledger.selection_block(
                    docket.video_id, candidate["start_s"], candidate["end_s"],
                    candidate.get("cause_number"), candidate.get("defendant_name"))
                if blocked:
                    log.info("  story memory: %s — %s", key, why)
                    continue
                if self.store.story_rendered(
                    key,
                    docket.video_id,
                    candidate.get("cause_number"),
                    candidate.get("start_s"),
                    candidate.get("end_s"),
                ):
                    log.info("  already rendered locally (same window or cause): %s — excluded from new selection", key)
                    continue
                eligible.append(candidate)

            # Re-rank the cases that already cleared safety and the rubric.
            #
            # Ranking is the rubric's total_score and nothing else.
            #
            # A second ranker (notoriety) and a third (banger) both used to sit
            # here. Both are retired to research/retired/ — see spec/SPEC.md §3.
            # Each was hand-fitted against a handful of cases, neither was ever
            # validated against a published outcome, and together they made the
            # order impossible to explain. One scorer that reads the transcript
            # and answers concrete questions replaces all three.
            if not eligible:
                log.info("  no case cleared the gates")
                self.store.mark_docket(docket.video_id, "no_eligible_cases")
                continue

            # BOYD_EDITORIAL_V2 PART 5: continuity breaks ties only inside the
            # configured window, after every gate, never as a multiplier.
            eligible = self._repeat_tiebreak(docket.video_id, eligible)
            for local_order, case in enumerate(eligible):
                candidates.append((docket, case, "new", docket_index * 10000 + local_order))

        if self._analyzer is not None:
            self._analyzer.reserved_calls = 0

        # The durable bank competes with today's dockets. This prevents a weak
        # fresh case from displacing a stronger unproduced story, while the
        # clip table removes a bank item as soon as production starts.
        excluded = {
            self.store.case_key(docket.video_id, case["start_s"])
            for docket, case, _source, _order in candidates
        }
        bank = self._bank_candidates(per_day, excluded)
        base_order = len(candidates)
        candidates.extend(
            (docket, case, source, base_order + order)
            for docket, case, source, order in bank
        )
        if bank:
            log.info("added %d unproduced bank candidate(s) to global selection", len(bank))

        # Old scored rows may contain more than one segment from the same cause.
        # Each segment expands to the same recalled-hearing story at production
        # time, so allowing both to compete wastes a second model/image attempt
        # on identical footage after a failure. Collapse those rows now and keep
        # the strongest editorial entry as the story representative.
        unique_stories: dict[tuple[Any, ...], tuple[discover.Docket, dict[str, Any], str, int]] = {}
        for item in candidates:
            docket, case, _source, _order = item
            windows = case.get("story_windows")
            if not windows and hasattr(self.store, "case_windows"):
                windows = self.store.case_windows(docket.video_id, case["start_s"])
            windows = windows or [[case["start_s"], case["end_s"]]]
            normalized = tuple((round(float(a), 3), round(float(b), 3)) for a, b in windows)
            case["story_windows"] = [[a, b] for a, b in normalized]
            signature = (docket.video_id, normalized)
            current = unique_stories.get(signature)
            if current is None or float(case.get("total_score") or 0) > float(current[1].get("total_score") or 0):
                unique_stories[signature] = item
        if len(unique_stories) != len(candidates):
            log.info("collapsed %d duplicate same-cause candidate row(s)", len(candidates) - len(unique_stories))
        candidates = list(unique_stories.values())

        if not candidates:
            log.info("nothing viable to process; no eligible bank fallback")
            self._write_daily_record([], [], [], "skipped_no_candidate")
            return []

        self._attach_competitor_matches(candidates, lead_transcripts)

        # A verified transcript match to a proven daily competitor is a lead,
        # never a source or safety bypass. Every candidate here already passed
        # the normal gates; lead strength ranks matched originals, then the
        # BOYD_EDITORIAL_V2 total ranks everything else.
        candidates.sort(key=lambda item: competitor.candidate_priority(item[1], item[3]))
        if self.cfg.get("output.bank_extras") and len(candidates) > per_day:
            log.info("banking %d globally ranked runner-up case(s)", len(candidates) - per_day)

        produced: list[dict[str, Any]] = []
        planned = 0
        attempted = 0
        failures: list[str] = []
        holds: list[str] = []
        budget_blocked: str | None = None
        for docket, case, source, _order in candidates:
            if len(produced) >= per_day:
                break
            if not dry_run and self._analyzer is not None:
                model_limit = int(self.cfg.get("analysis.max_model_calls_per_run", 20))
                used_total = int(getattr(self._analyzer, "calls_used", 0)) + int(
                    getattr(self, "_thumbnail_model_calls_used", 0)
                )
                minimum_needed = (
                    int(bool(self.cfg.get("analysis.gates.recheck_selection", True)))
                    + int(bool(self.cfg.get("analysis.producer_brain.enabled", True)))
                    + int(self.cfg.get("packaging.thumbnail.mode") == "direct_gen")
                    # 2026-09-19: the thumbnail copy review is no longer a
                    # direct_gen-only call — the legacy compositor runs it too
                    # before its render — so a legacy producer bundle needs
                    # this third call reserved or it would start work it
                    # cannot finish inside the run limit.
                    + int(bool(self.cfg.get("analysis.producer_brain.enabled", True))
                          and self.cfg.get("packaging.thumbnail.mode") != "direct_gen")
                )
                if used_total >= model_limit:
                    log.error("daily Sol limit is exhausted; remaining candidates stay banked")
                    budget_blocked = f"Sol call limit exhausted ({model_limit}/{model_limit})"
                    break
                if model_limit - used_total < minimum_needed:
                    budget_blocked = (
                        f"only {model_limit - used_total} Sol call(s) remain; "
                        f"a complete bundle needs at least {minimum_needed}"
                    )
                    log.error("%s; remaining candidates stay banked", budget_blocked)
                    break
            if (
                not dry_run
                and self.cfg.get("packaging.thumbnail.mode") == "direct_gen"
                and int(getattr(self, "_thumbnail_images_remaining", 9)) < 3
            ):
                log.error("daily thumbnail-image limit cannot fund another complete A/B/C set")
                budget_blocked = "thumbnail-image limit cannot fund another A/B/C set"
                break
            key = self.store.case_key(docket.video_id, case["start_s"])
            if self.store.case_published(key):
                log.info("  case %s already published — skipping", key)
                continue
            if dry_run:
                log.info(
                    "  [dry-run] global pick: %s (score %.1f, %s) — %s",
                    key, case["total_score"], source, case["summary"][:90],
                )
                planned += 1
                if planned >= per_day:
                    break
                continue

            if self.cfg.get("analysis.gates.recheck_selection", True):
                transcript = get_transcript(docket.video_id, self.work / docket.video_id)
                meta = _docket_meta(docket)
                confirmed, why = self.analyzer.confirm_selection(transcript, case, meta)
                if not confirmed:
                    log.warning("  selection dropped on re-check: %s", why)
                    self.store.save_case(docket.video_id, case, None)
                    continue
                log.info("  re-check passed (score %.1f)", case["total_score"])

            try:
                attempted += 1
                result = self.produce(docket, case)
            except StoryReuseError as exc:
                attempted -= 1
                log.info("  story memory blocked %s: %s", key, exc)
                holds.append(f"{key}: StoryReuseError: {exc}")
                continue
            except (TooShortError, EditorialHoldError, capfit.CapFitError) as exc:
                attempted -= 1
                log.info("  editorial hold for %s: %s", key, exc)
                holds.append(f"{key}: {type(exc).__name__}: {exc}")
                continue
            except Exception as exc:
                log.error("  production failed for %s: %s", key, exc)
                log.debug(traceback.format_exc())
                failures.append(f"{key}: {type(exc).__name__}: {exc}")
                continue

            manifest_path = Path(result["review_dir"]) / "manifest.json"
            try:
                evidence = readiness.validate_candidate_bundle(manifest_path)
                result["readiness"] = evidence
            except readiness.ReadinessError as exc:
                result["readiness"] = {"ready": False, "error": str(exc)}
                log.error("  candidate bundle is not ready: %s", exc)
                self.store.reset_unpublished_clips(key)
                failures.append(f"{key}: readiness: {exc}")
                continue

            try:
                report = publish_pair(
                    self.cfg, self.store,
                    longform=result["longform"],
                    short=result["short"],
                    context={"hook_line": result["package"]["hook_line"]},
                )
            except Exception as exc:
                log.error("  publish failed (clip is rendered and retained): %s", exc)
                log.debug(traceback.format_exc())
                report = {"error": str(exc), "skipped": ["publish raised; use boyd approve"]}
            result["publish"] = report
            for note in report.get("skipped", []):
                log.info("  publish: %s", note)
            produced.append(result)
            self.store.mark_docket(docket.video_id, "complete")
            log.info("  done -> %s", result["review_dir"])

        if dry_run:
            log.info("  [dry-run] all dockets left pending for a real run")
            self._write_daily_record(candidates, [], [], "dry_run")
        elif not produced:
            if attempted or budget_blocked:
                if budget_blocked:
                    failures.append(budget_blocked)
                self._write_daily_record(candidates, [], failures, "failed")
                raise DailyRunError(
                    f"{attempted} viable candidate(s) failed; no complete review bundle. "
                    + " | ".join(failures[:3])
                )
            log.info("no candidate produced; %d candidate(s) were intentionally held", len(holds))
            self._write_daily_record(candidates, [], holds, "skipped_editorial_hold")
        else:
            self._write_daily_record(candidates, produced, failures, "review_ready")
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
        """SAFETY_RULES R7: every clip must be reconstructible from its record."""
        manifest = {
            "spec_version": SPEC_VERSION,
            "status": "candidate",
            "review_required": True,
            "generated_at": _now(),
            "source": {
                "video_id": docket.video_id,
                "url": docket.url,
                "title": docket.title,
                "docket_date": docket.docket_date,
                "session": docket.session,
                # Which judge this clip belongs to. Defaulted rather than
                # required, so a docket object built before this field existed
                # (or rebuilt from a stored row) still stamps the Boyd
                # manifest it always did.
                "judge_id": getattr(docket, "judge_id", discover.DEFAULT_JUDGE_ID),
                "judge_name": getattr(docket, "judge_name", discover.DEFAULT_JUDGE_NAME),
            },
            "case": {
                "start_s": case["start_s"],
                "end_s": case["end_s"],
                "story_windows": case.get("story_windows") or [[case["start_s"], case["end_s"]]],
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
            "usage": {
                "model_calls": list(getattr(self.analyzer, "usage_events", [])),
                "thumbnail_model_calls": int(getattr(self, "_thumbnail_model_calls_used", 0)),
                "sol_calls_total": int(getattr(self.analyzer, "calls_used", 0)) + int(
                    getattr(self, "_thumbnail_model_calls_used", 0)
                ),
                "thumbnail_images_reported": (
                    int(self.cfg.get("output.max_thumbnail_images_per_run", 9))
                    - int(getattr(self, "_thumbnail_images_remaining", self.cfg.get("output.max_thumbnail_images_per_run", 9)))
                ),
                "token_usage": None,
                "estimated_cost": None,
            },
            # SHORTS_EDITOR_V2 verdict: scores, refusal reason, tile map,
            # render QC — present whether or not a short was made.
            "short_editor": result.get("short_editor"),
            "outputs": {
                k: dict(v)
                for k, v in result.items()
                if k in ("longform", "short", "thumbnail") and v
            },
        }
        manifest_path = review_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        try:
            readiness.stamp_manifest(manifest_path)
        except readiness.ReadinessError as exc:
            log.warning("  readiness stamp incomplete: %s", exc)

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
            why = (result.get("short_editor") or {}).get("refusal") or "case was not shortable"
            lines += ["SHORT", f"  none — {why}", ""]
        lines += [
            "DESCRIPTION (long-form)",
            "-" * 72,
            lf["description"],
            "",
            "-" * 72,
            "Approve:  boyd approve " + result["case_key"] + " --concept A|B|C",
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


SUBJECT_FACE_MIN_REL_WIDTH = 0.6   # a face this much narrower than the largest is the gallery
SUBJECT_FACE_EDGE_FRAC = 0.12      # a face centred this close to a tile edge is half out of frame


def choose_subject_face(inside: list[tuple[float, float, float, float, float]], role: str,
                        min_rel: float = SUBJECT_FACE_MIN_REL_WIDTH,
                        edge: float = SUBJECT_FACE_EDGE_FRAC) -> tuple[float, float, float, float, float] | None:
    """Which detected face is the subject of a tile. `inside` rows are
    (width_px, fx, fy, fw, fh) with fx/fy the face centre as a fraction of
    the tile.

    Boyd's tile holds one person: the largest face. The courtroom tile does
    not: the defendant stands at the lectern left of centre and defence
    counsel stands beside them nearer the camera, so "largest face" framed
    the attorney and cut the defendant off at the edge (Robinson fx 0.82,
    Garcia fx 0.77, measured 2026-09-06; Flores stands at 0.28). The subject
    is chosen among the faces that are still substantial (>= min_rel of the
    widest, which drops the gallery) and not centred within `edge` of a tile
    edge (which drops the prosecutor half out of frame at far left): the
    MIDDLE face when three or more stand at the lectern (Alonzo: counsel on
    both sides of her, measured 0.13 / 0.35 / 0.75), the LEFT face when two
    do (Robinson 0.25 / 0.70, Diaz 0.40 / 0.75, Garcia 0.42 / 0.77 once the
    edge prosecutor is dropped)."""
    if not inside:
        return None
    if role == "boyd":
        return max(inside)
    wmax = max(f[0] for f in inside)
    substantial = [f for f in inside if f[0] >= min_rel * wmax]
    framed = [f for f in substantial if edge <= f[1] <= 1.0 - edge]
    pool = sorted(framed or substantial or inside, key=lambda f: f[1])
    if len(pool) >= 3:
        return pool[len(pool) // 2]
    return pool[0]


def split_thumbnail_quote(pkg: dict[str, Any]) -> tuple[str, str]:
    """Split the thumbnail quote into its white and yellow halves.

    spec/PACKAGING.md §Thumbnails rule 4: "The emotionally loaded half of the
    sentence goes yellow, the setup stays white — `This` / `cop was lying!`.
    Split mid-sentence, not by line."

    Which half is the loaded one is a judgement about meaning, so it comes from
    the packaging model as `thumbnail_quote_yellow` and is accepted only when it
    is a real suffix of the quote — otherwise the two fields disagree and the
    rendered thumbnail would not be the quote the manifest records.

    The fallback is a word-count midpoint. It is mechanical and will sometimes
    colour the wrong clause, so it warns rather than passing itself off as the
    house style.
    """
    quote = (pkg.get("thumbnail_quote") or "").strip()
    if not quote:
        raise ValueError("packaging produced no thumbnail_quote")

    yellow = (pkg.get("thumbnail_quote_yellow") or "").strip()
    if yellow and quote.endswith(yellow) and len(yellow) < len(quote):
        return quote[: -len(yellow)].strip(), yellow

    if yellow:
        log.warning(
            "  thumbnail: thumbnail_quote_yellow (%r) is not a suffix of "
            "thumbnail_quote (%r) — falling back to a midpoint split", yellow, quote,
        )
    else:
        log.warning(
            "  thumbnail: packaging returned no thumbnail_quote_yellow — "
            "splitting at the midpoint, which may colour the wrong clause "
            "(spec/PACKAGING.md rule 4)"
        )

    words = quote.split()
    cut = max(1, len(words) // 2)
    return " ".join(words[:cut]), " ".join(words[cut:])


# Schema enum values are machine tokens; naive title-casing put literal
# "Other before Judge Stephanie Boyd" into a published description.
PROCEEDING_LABELS = {
    "arraignment": "An arraignment",
    "plea": "A plea hearing",
    "sentencing": "A sentencing",
    "bond_hearing": "A bond hearing",
    "probation_revocation": "A probation revocation hearing",
    "motion_hearing": "A motion hearing",
    "status_conference": "A status conference",
    "trial_segment": "Trial proceedings",
    "administrative": "A court proceeding",
    "other": "A court proceeding",
}


def _proceeding_label(proceeding_type: str) -> str:
    return PROCEEDING_LABELS.get(
        proceeding_type, proceeding_type.replace("_", " ").capitalize()
    )


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
