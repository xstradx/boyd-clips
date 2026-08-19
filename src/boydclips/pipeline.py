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

from . import diarize, discover, momentrun, render, thumbnail
from .analyze import Analyzer, RefusalError
from .config import SPEC_VERSION, Config, load_config
from .publish import publish_pair
from .state import Store
from .transcribe import Word, get_transcript, hhmmss

log = logging.getLogger("boydclips")


class TooShortError(RuntimeError):
    """The case is under the long-form floor once dead air is removed.

    Raised before the encode. run_daily() already treats a production failure
    as "skip this case, keep the docket pending", which is the right handling:
    a case that is mostly silence is not a failure of the run, it is a case
    that should not be published.
    """


class PausedError(RuntimeError):
    """The tray switch is RED. See tools/boyd-toggle.ps1."""


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

    def analyze_docket(self, docket: discover.Docket) -> list[dict[str, Any]]:
        work = self.work / docket.video_id
        work.mkdir(parents=True, exist_ok=True)

        cached = work / "scored.json"
        if cached.exists():
            scored = json.loads(cached.read_text(encoding="utf-8"))
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
        meta = {"title": docket.title, "docket_date": docket.docket_date, "url": docket.url}

        lf_cfg = self.cfg.require("output.longform")
        sh_cfg = self.cfg.require("output.short")

        pad_before = lf_cfg.get("pad_before_s", 4.0)
        pad_after = lf_cfg.get("pad_after_s", 3.0)

        # A recessed-and-recalled hearing is one case in several sittings; the
        # long-form has to carry all of them or it ends on the recess with the
        # ruling missing. See Store.case_windows.
        windows = self.store.case_windows(docket.video_id, case["start_s"]) or [
            (case["start_s"], case["end_s"])
        ]

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
        pkg_case = dict(case)
        pkg_case["start_s"] = windows[0][0]
        pkg_case["end_s"] = windows[-1][1]

        log.info("  package: writing titles and description")
        pkg = self.analyzer.package(transcript, pkg_case, meta, SPEC_VERSION)
        if not pkg["hook_verified"]:
            log.warning(
                "  package: hook line not found verbatim in transcript — "
                "CONTENT_SPEC §6 requires titles the clip proves. Flagging for review."
            )
        lf_windows = [
            (max(0.0, s - pad_before), e + pad_after) for s, e in windows
        ]
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
        source, offset = render.download_section(
            docket.video_id, lf_start, lf_end, work / f"{case_key.replace(':', '_')}.mp4"
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
        if planned_s > cap_s:
            log.warning(
                "  render: long-form %.0fs exceeds the %.0fs cap — trimming to the cap "
                "on a piece boundary", planned_s, cap_s,
            )
            capped: list[render.Segment] = []
            budget = cap_s
            for piece in lf_pieces:
                if budget <= 0:
                    break
                if piece.duration <= budget:
                    capped.append(piece)
                    budget -= piece.duration
                else:
                    # Cut mid-piece rather than dropping it whole: dropping the
                    # last piece is what loses the ruling.
                    capped.append(render.Segment(piece.start_s, piece.start_s + budget))
                    budget = 0
            lf_pieces = capped
            planned_s = sum(p.duration for p in lf_pieces)

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
                log.warning("  render: intro enabled but no sting found — going out unbranded")
            else:
                log.info("  render: intro %s", intro.name)

        log.info("  render: long-form (%d pieces, %.0fs)", len(lf_pieces), planned_s)
        lf_path = review_dir / "longform.mp4"
        lf_duration = render.render_longform(
            source, offset, lf_pieces, lf_cfg, lf_path, crop=crop, intro=intro,
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
            },
            "short": None,
        }

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
            self._write_manifest(review_dir, docket, case, pkg, result)
            return result

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
        }

        try:
            hook_at = max(0.0, case["hook_start_s"] - offset)
            render.extract_thumbnail(source, hook_at, review_dir / "thumbnail.jpg")
            # publish.py attaches `thumbnail_quote.jpg`; nothing in the pipeline
            # ever wrote one. The builders existed and were never wired in, so
            # every upload would have gone out on whatever frame YouTube picked
            # — against spec/PACKAGING.md, which is the house style and the one
            # measurable difference between this channel and a competitor doing
            # 414K on the same judge.
            #
            # thumbnail.build produces the construction Nathan approved on
            # Thompson (2026-08-17): traced judge over the courtroom plate,
            # feathered and unstroked, arrow, quote split white -> yellow.
            white, yellow = split_thumbnail_quote(pkg)
            thumbnail.build(
                source, hook_at, white, yellow,
                review_dir / "thumbnail_quote.jpg",
                self.cfg.get("packaging.thumbnail", {}),
            )
            log.info("  thumbnail: house style -> thumbnail_quote.jpg  (%r / %r)",
                     white, yellow)
        except Exception as exc:  # a missing thumbnail must not fail the run
            log.warning("  thumbnail: house-style thumbnail not produced (%s)", exc)

        self._write_manifest(review_dir, docket, case, pkg, result)
        return result

    # ------------------------------------------------------------------ driver

    def run_case(self, case_key: str, dry_run: bool = False) -> dict[str, Any] | None:
        """Render one specific already-scored case, chosen by the operator.

        run_daily() picks the top scorer; this renders whoever you name. The
        case must already exist in the store — this deliberately does not
        re-analyse, so an operator cannot use it to bypass the safety gate on
        a case that was never scored.
        """
        case = self.store.get_case(case_key)
        if case is None:
            log.error("unknown case %s — run `boyd bank` to list available cases", case_key)
            return None

        safety = case.get("safety", {})
        if not safety.get("safety_pass"):
            rules = ", ".join(safety.get("safety_rule_violations") or []) or "unspecified"
            log.error("case %s failed the safety gate (%s) — refusing to render", case_key, rules)
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

        log.info("case %s — %s (score %.1f)", case_key,
                 case.get("defendant_name") or "?", case.get("total_score") or 0.0)

        if dry_run:
            log.info("  [dry-run] would render: %s", (case.get("summary") or "")[:100])
            return None

        result = self.produce(docket, case)
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

        if dry_run:
            log.info("  [dry-run] would render %.0f-%.0fs of %s",
                     case["start_s"], case["end_s"], video_id)
            return None

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
                log.info("  no case cleared the gates — nothing to publish today")
                self.store.mark_docket(docket.video_id, "no_eligible_cases")
                continue

            produced_this_docket = False
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

                # Last gate before anything is downloaded. Batch scoring sees a
                # narrowed transcript; this re-checks the pick against all of
                # it, because safety judgements have been observed to move
                # between runs and this is the point where being wrong costs
                # the most.
                if self.cfg.get("analysis.gates.recheck_selection", True):
                    transcript = get_transcript(docket.video_id, self.work / docket.video_id)
                    meta = {"title": docket.title, "docket_date": docket.docket_date,
                            "url": docket.url}
                    confirmed, why = self.analyzer.confirm_selection(transcript, case, meta)
                    if not confirmed:
                        log.warning("  selection dropped on re-check: %s", why)
                        self.store.save_case(docket.video_id, case, None)
                        continue
                    log.info("  re-check passed (score %.1f)", case["total_score"])

                produced_this_docket = True

                try:
                    result = self.produce(docket, case)
                except Exception as exc:
                    log.error("  production failed: %s", exc)
                    log.debug(traceback.format_exc())
                    produced_this_docket = False
                    continue

                # Publishing must not be able to abort the run. An escape here
                # would skip cleanup and leave every remaining docket in `new`
                # unprocessed — and, before the is_terminal fix, permanently
                # consumed. The clip is already rendered and on disk either
                # way, so a publish failure is recoverable via `boyd approve`.
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
                for platform, info in report.get("short", {}).items():
                    if "url" in info:
                        log.info("  published short to %s: %s", platform, info["url"])
                    else:
                        log.warning("  %s: %s", platform, info.get("error"))
                if report.get("longform", {}).get("url"):
                    log.info("  published long-form: %s", report["longform"]["url"])

                produced.append(result)
                log.info("  done -> %s", result["review_dir"])

            # Only a docket that actually yielded a clip is finished. Marking
            # it complete after a dry run, a swallowed production failure, or
            # an all-skipped pick list would assert work that never happened
            # and make the docket unreachable on later runs.
            if produced_this_docket:
                self.store.mark_docket(docket.video_id, "complete")
            elif dry_run:
                log.info("  [dry-run] docket left pending for a real run")
            else:
                log.warning("  docket left pending — nothing was produced")

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
