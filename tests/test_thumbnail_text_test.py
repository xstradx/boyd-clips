"""The text-only A/B/C thumbnail experiment: build contract and its controls.

Written 2026-09-19 for Nathan's request to hold the picture still and A/B test
what the thumbnail SAYS. The picture is supplied (one shared base with the
arrow already baked in upstream); this module's only job is the words, and the
tests below are the experiment's own controls:

  * a real build on a real 1280x720 base, then `validate_experiment` on it;
  * negative controls for every gate (blank, duplicate, missing emphasis,
    missing evidence, missing base, missing font, too long to read, ink outside
    the rectangle, profanity) - each with the proof that a refused build wrote
    nothing at all;
  * tamper controls against the validator: swapped image, modified background,
    changed base, changed title, missing file, missing label.

The gates that carry a defect are constructed here rather than borrowed from an
old render, and the ink-escape control deliberately breaks the margin estimate
so the gate has to catch it in the build path.

No network, no model calls, no publishing. `python tests/test_thumbnail_text_test.py`
runs the whole file without pytest; pytest collects it as well.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import thumbnail_text_test as ttt  # noqa: E402
from boydclips.thumbnail_text_test import (  # noqa: E402
    TextRectangle,
    TextVariant,
    ThumbnailTextTestError,
    Typography,
    build_text_only_experiment,
    validate_experiment,
)

TITLE = "Judge Boyd audits the whole docket"
EVIDENCE = "Judge Boyd: \"I audit the court in every single hearing.\""
VARIANTS = (
    TextVariant("A", "Audit the court", "court"),
    TextVariant("B", "The court got audited", "audited"),
    TextVariant("C", "She audited the court live", "audited the court"),
)


class _Raises:
    """A pytest-free `pytest.raises` that also checks the gate codes."""

    def __init__(self, *codes: str):
        self.codes = codes
        self.error: ThumbnailTextTestError | None = None

    def __enter__(self) -> "_Raises":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            raise AssertionError(f"expected a refusal carrying {self.codes}, got none")
        if not issubclass(exc_type, ThumbnailTextTestError):
            return False
        self.error = exc
        missing = [code for code in self.codes if code not in exc.codes]
        if missing:
            raise AssertionError(
                f"refusals {exc.codes} did not include {missing}: {exc}"
            )
        return True


def _make_base(path: Path) -> Path:
    """A real 1280x720 picture on disk - not flat, so pixel comparisons mean
    something. This stands in for the shared base; the builder never edits it."""
    image = Image.new("RGB", (1280, 720), (34, 42, 56))
    draw = ImageDraw.Draw(image)
    for x in range(0, 1280, 64):
        draw.rectangle([x, 230, x + 28, 560], fill=(92, 46, 44))
    draw.ellipse([860, 200, 1180, 640], fill=(104, 88, 72))
    draw.rectangle([0, 0, 1280, 96], fill=(20, 24, 32))
    image.save(path)
    return path


def _workspace():
    return tempfile.TemporaryDirectory(prefix="ttt_test_")


def _receipt(outdir: Path) -> dict:
    return json.loads((outdir / "thumbnail-text-only.json").read_text(encoding="utf-8"))


def _rebuild(outdir: Path, **overrides) -> dict:
    kwargs = dict(
        base=overrides.pop("base"),
        title=overrides.pop("title", TITLE),
        variants=overrides.pop("variants", VARIANTS),
        evidence=overrides.pop("evidence", EVIDENCE),
        outdir=outdir,
    )
    kwargs.update(overrides)
    return build_text_only_experiment(**kwargs)


def _colour_mask(image: Image.Image, colour: tuple[int, int, int]) -> Image.Image:
    """Exact-colour ink mask (anti-aliased edge pixels are deliberately out)."""
    from PIL import ImageChops

    solid = Image.new("RGB", image.size, colour)
    return ImageChops.difference(image, solid).convert("L").point(
        lambda value: 255 if value == 0 else 0
    )


# --------------------------------------------------------------------------
# positive build + receipt contract
# --------------------------------------------------------------------------
def test_build_writes_receipt_with_required_bindings() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        base = _make_base(tmp / "base.png")
        out = tmp / "out"
        receipt = _rebuild(out, base=base)

        assert receipt["receipt_type"] == "thumbnail_text_only"
        assert receipt["renderer"]["version"] == ttt.RENDERER_VERSION
        assert receipt["fixed_title"] == TITLE
        assert receipt["base"]["sha256"] == ttt._sha256_file(base)
        assert receipt["base"]["pixel_sha256"] == ttt._sha256_image(Image.open(base))
        assert receipt["hashes"]["font_sha256"] == ttt._sha256_file(ttt.DEFAULT_FONT)
        assert receipt["hashes"]["config_sha256"]
        assert receipt["hashes"]["receipt_checksum_sha256"]
        assert "NOT a signature" in receipt["hashes"]["checksum_note"]
        assert receipt["text_rectangle"] == ttt._coerce_rect(None).as_dict()
        assert [v["label"] for v in receipt["variants"]] == ["A", "B", "C"]
        for variant in receipt["variants"]:
            assert Path(variant["png_path"]).is_file()
            assert Path(variant["svg_path"]).is_file()
            assert Path(variant["layer_path"]).is_file()
            assert variant["png_sha256"]
            assert variant["text"]
            assert variant["emphasis"] in variant["text"]
        assert (out / "thumbnail-text-only.json").is_file()


def test_evidence_is_recorded_as_supplied_not_verified() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        evidence = receipt["source_evidence"]
        assert evidence["present"] is True
        assert evidence["verified"] is False
        assert receipt["not_claimed"]


def test_exports_are_editable_and_keep_the_words_verbatim() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        mixed_case = "She audited the court live"
        for variant in receipt["variants"]:
            layer = json.loads(Path(variant["layer_path"]).read_text(encoding="utf-8"))
            svg = Path(variant["svg_path"]).read_text(encoding="utf-8")
            assert layer["text"] == variant["text"]
            assert " ".join(line["text"] for line in layer["lines"]) == variant["text"]
            assert "<text" in svg and "<tspan" in svg
            assert ttt.EMPHASIS_YELLOW in svg
            assert "font-weight=\"700\"" in svg
            assert "Montserrat" in svg
        # natural sentence case is never uppercased for the export
        c_layer = json.loads(
            Path(receipt["variants"][2]["layer_path"]).read_text(encoding="utf-8")
        )
        from_lines = ttt._normalize_whitespace(
            " ".join(line["text"] for line in c_layer["lines"])
        )
        assert from_lines == mixed_case


def test_variant_invariants_hold_on_the_written_files() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        base = _make_base(tmp / "base.png")
        receipt = _rebuild(tmp / "out", base=base)
        rect = TextRectangle(**receipt["text_rectangle"])
        base_image = Image.open(base).convert("RGB")
        sizes = {(Image.open(v["png_path"]).size) for v in receipt["variants"]}
        assert sizes == {(1280, 720)}
        assert len({v["font_px"] for v in receipt["variants"]}) == 1  # one type scale
        images = [Image.open(v["png_path"]).convert("RGB") for v in receipt["variants"]]
        for image in images:
            assert ttt._bbox_within(ttt._diff_bbox(image, base_image), rect)
            assert ttt._changed_pixels(image, base_image) > 0
        for i in range(len(images)):
            for j in range(i + 1, len(images)):
                diff = ttt._diff_bbox(images[i], images[j])
                assert diff is not None
                assert ttt._bbox_within(diff, rect)
        assert len({v["png_sha256"] for v in receipt["variants"]}) == 3
        assert len({v["normalized_text"] for v in receipt["variants"]}) == 3
        # one layout policy: same rectangle, same origin, same band, same type
        # scale - the variants may only differ in their words.
        layouts = [
            json.loads(Path(v["layer_path"]).read_text(encoding="utf-8"))
            for v in receipt["variants"]
        ]
        assert len({line["x"] for layout in layouts for line in layout["lines"]}) == 1
        by_line_count: dict[int, set[tuple[int, ...]]] = {}
        for layout in layouts:
            baselines = tuple(line["baseline_y"] for line in layout["lines"])
            by_line_count.setdefault(len(baselines), set()).add(baselines)
        assert all(len(group) == 1 for group in by_line_count.values()), (
            "variants with the same number of lines must share the same band"
        )
        assert len({layout["typography"]["font_px"] for layout in layouts}) == 1
        assert len({json.dumps(layout["text_rectangle"], sort_keys=True)
                    for layout in layouts}) == 1


def test_emphasis_marks_only_the_supplied_substring() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        base = _make_base(tmp / "base.png")
        receipt = _rebuild(
            tmp / "emphasis", base=base,
            variants=(
                # A is entirely yellow: its whole headline IS the emphasis run.
                TextVariant("A", "Audit the court", "Audit the court"),
                TextVariant("B", "The court got audited", "court"),
                TextVariant("C", "She audited the court live", "audited the court"),
            ),
        )
        masks = {}
        for record in receipt["variants"]:
            image = Image.open(record["png_path"]).convert("RGB")
            yellow = _colour_mask(image, (254, 251, 3))
            white = _colour_mask(image, (255, 255, 255))
            yellow_pixels = sum(yellow.histogram()[255:])
            white_pixels = sum(white.histogram()[255:])
            assert yellow_pixels > 0, f"{record['label']}: no yellow ink"
            masks[record["label"]] = (yellow.getbbox(), white.getbbox())
            if record["label"] == "A":
                assert white_pixels == 0, "a fully emphasised headline must have no white ink"
            else:
                assert white_pixels > 0, f"{record['label']}: no white ink"
        # B is "The court got audited" with only "court" yellow: the white run
        # starts the line, so the yellow ink must start to its right.
        b_yellow, b_white = masks["B"]
        assert b_white is not None
        assert b_yellow[0] > b_white[0]


def test_rebuild_is_byte_deterministic() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        base = _make_base(tmp / "base.png")
        first = _rebuild(tmp / "one", base=base)
        second = _rebuild(tmp / "two", base=base)
        assert [v["png_sha256"] for v in first["variants"]] == [
            v["png_sha256"] for v in second["variants"]
        ]
        assert first["hashes"]["config_sha256"] == second["hashes"]["config_sha256"]


# --------------------------------------------------------------------------
# validate_experiment
# --------------------------------------------------------------------------
def test_validate_accepts_a_good_experiment() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        report = validate_experiment(receipt)
        assert report["ok"] is True, report["failures"]
        assert report["failures"] == []
        assert report["checks"]["re_render"] == "compared"
        from_disk = validate_experiment(tmp / "out" / "thumbnail-text-only.json")
        assert from_disk["ok"] is True


def test_validate_reports_a_missing_receipt() -> None:
    with _workspace() as tmp:
        report = validate_experiment(Path(tmp) / "nope.json")
        assert report["ok"] is False
        assert [f["code"] for f in report["failures"]] == ["RECEIPT_MISSING"]


def test_validate_catches_a_swapped_image() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        a, b = receipt["variants"][0], receipt["variants"][1]
        shutil.copy(a["png_path"], b["png_path"])
        codes = [f["code"] for f in validate_experiment(receipt)["failures"]]
        assert "VARIANT_BYTES_HASH_MISMATCH" in codes
        assert "VARIANT_SWAPPED" in codes


def test_validate_catches_a_modified_background() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        path = Path(receipt["variants"][1]["png_path"])
        image = Image.open(path).convert("RGB")
        image.putpixel((4, 4), (255, 0, 255))  # far outside the text rectangle
        image.save(path)
        codes = [f["code"] for f in validate_experiment(receipt)["failures"]]
        assert "VARIANT_PIXEL_HASH_MISMATCH" in codes
        assert "BACKGROUND_MODIFIED" in codes


def test_validate_catches_a_changed_base() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        base = _make_base(tmp / "base.png")
        receipt = _rebuild(tmp / "out", base=base)
        image = Image.open(base).convert("RGB")
        image.putpixel((600, 700), (255, 0, 255))
        image.save(base)
        codes = [f["code"] for f in validate_experiment(receipt)["failures"]]
        assert "BASE_BYTES_HASH_MISMATCH" in codes
        assert "BASE_PIXEL_HASH_MISMATCH" in codes


def test_validate_catches_a_changed_title() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        tampered = json.loads(json.dumps(receipt))
        tampered["fixed_title"] = "A different title entirely"
        codes = [f["code"] for f in validate_experiment(tampered)["failures"]]
        assert "TITLE_CHANGED" in codes
        assert "RECEIPT_CHECKSUM_MISMATCH" in codes
        # the config basis is untouched, so its own hash still matches: the
        # failure is the title disagreeing with the config that was built.
        assert "CONFIG_HASH_MISMATCH" not in codes


def test_validate_catches_a_changed_style_config() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        tampered = json.loads(json.dumps(receipt))
        tampered["config"]["typography"]["stroke_ratio"] = 0.4
        codes = [f["code"] for f in validate_experiment(tampered)["failures"]]
        assert "CONFIG_HASH_MISMATCH" in codes
        assert "TYPOGRAPHY_CHANGED" in codes


def test_validate_catches_a_reworded_variant() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        layer_path = Path(receipt["variants"][2]["layer_path"])
        layer = json.loads(layer_path.read_text(encoding="utf-8"))
        layer["lines"][0]["text"] = layer["lines"][0]["text"].upper()
        layer_path.write_text(json.dumps(layer), encoding="utf-8")
        codes = [f["code"] for f in validate_experiment(receipt)["failures"]]
        assert "VARIANT_TEXT_CHANGED" in codes


def test_validate_catches_a_missing_file_and_a_missing_label() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        Path(receipt["variants"][2]["png_path"]).unlink()
        tampered = json.loads(json.dumps(receipt))
        tampered["variants"] = [
            {k: v for k, v in record.items() if k != "label"}
            if record["label"] == "B" else record
            for record in tampered["variants"]
        ]
        codes = [f["code"] for f in validate_experiment(tampered)["failures"]]
        assert "VARIANT_FILE_MISSING" in codes
        assert "VARIANT_LABELS" in codes


# --------------------------------------------------------------------------
# negative controls: every gate, and no side effects when it fires
# --------------------------------------------------------------------------
def _expect_refusal(tmp: Path, codes: tuple[str, ...], **overrides) -> None:
    out = tmp / "out"
    with _Raises(*codes) as caught:
        _rebuild(out, **overrides)
    assert caught.error is not None
    assert not out.exists(), "a refused build must write nothing at all"


def test_blank_headline_is_refused() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        _expect_refusal(
            tmp, ("BLANK_HEADLINE",), base=_make_base(tmp / "base.png"),
            variants=(
                TextVariant("A", "   ", "court"),
                TextVariant("B", "The court got audited", "audited"),
                TextVariant("C", "She audited the court live", "audited the court"),
            ),
        )


def test_duplicate_headline_is_refused() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        _expect_refusal(
            tmp, ("DUPLICATE_HEADLINE",), base=_make_base(tmp / "base.png"),
            variants=(
                TextVariant("A", "Audit the court", "court"),
                TextVariant("B", "Audit the  court", "court"),
                TextVariant("C", "She audited the court live", "audited the court"),
            ),
        )


def test_wrong_labels_are_refused() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        _expect_refusal(
            tmp, ("VARIANT_LABELS",), base=_make_base(tmp / "base.png"),
            variants=(
                TextVariant("A", "Audit the court", "court"),
                TextVariant("B", "The court got audited", "audited"),
                TextVariant("D", "She audited the court live", "audited the court"),
            ),
        )


def test_emphasis_that_is_not_in_the_headline_is_refused() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        base = _make_base(tmp / "base.png")
        _expect_refusal(
            tmp, ("EMPHASIS_NOT_FOUND",), base=base,
            variants=(
                TextVariant("A", "Audit the court", "judge"),
                TextVariant("B", "The court got audited", "audited"),
                TextVariant("C", "She audited the court live", "audited the court"),
            ),
        )
        _expect_refusal(
            tmp, ("EMPHASIS_NOT_EXACT",), base=base,
            variants=(
                TextVariant("A", "Audit the court", "COURT"),
                TextVariant("B", "The court got audited", "audited"),
                TextVariant("C", "She audited the court live", "audited the court"),
            ),
        )


def test_missing_evidence_base_and_font_are_refused() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        base = _make_base(tmp / "base.png")
        _expect_refusal(tmp, ("MISSING_EVIDENCE",), base=base, evidence="   ")
        _expect_refusal(tmp, ("BASE_MISSING",), base=tmp / "not-there.png")
        _expect_refusal(
            tmp, ("FONT_MISSING",), base=base,
            typography=Typography(font_path=tmp / "no-such-font.ttf"),
        )


def test_profanity_in_channel_text_is_refused() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        _expect_refusal(
            tmp, ("PROFANITY_IN_TEXT",), base=_make_base(tmp / "base.png"),
            variants=(
                TextVariant("A", "Audit the fucking court", "fucking"),
                TextVariant("B", "The court got audited", "audited"),
                TextVariant("C", "She audited the court live", "audited the court"),
            ),
        )


def test_a_headline_that_cannot_be_fitted_is_refused_before_any_output() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        _expect_refusal(
            tmp, ("TEXT_TOO_LONG",), base=_make_base(tmp / "base.png"),
            rectangle=(56, 30, 320, 150),
            variants=(
                TextVariant(
                    "A",
                    "Audit the court and every single hearing it ever held "
                    "in this county without a single transcript",
                    "court",
                ),
                TextVariant("B", "The court got audited", "audited"),
                TextVariant("C", "She audited the court live", "audited the court"),
            ),
        )


def test_ink_that_escapes_the_text_rectangle_is_refused() -> None:
    """Control for the ink gate: the margin estimate is deliberately broken, so
    the drawn shadow reaches outside the rectangle and the build must refuse
    instead of shipping a base the builder was not allowed to touch."""
    with _workspace() as tmp:
        tmp = Path(tmp)
        base = _make_base(tmp / "base.png")
        out = tmp / "out"
        original = ttt._ink_margins
        ttt._ink_margins = lambda font_px, typo: (0, 0, 0)
        try:
            with _Raises("INK_OUTSIDE_TEXT_RECT") as caught:
                build_text_only_experiment(
                    base=base,
                    title=TITLE,
                    variants=VARIANTS,
                    evidence=EVIDENCE,
                    outdir=out,
                    rectangle=(120, 300, 1160, 520),
                    typography=Typography(
                        max_font_px=64,
                        min_font_px=64,
                        rect_padding_px=0,
                        shadow_offset_ratio=0.9,
                        shadow_blur_ratio=0.5,
                    ),
                )
        finally:
            ttt._ink_margins = original
        assert caught.error is not None
        assert not out.exists()


def test_receipt_is_a_checksum_not_a_signature() -> None:
    """Recomputing the checksum after tampering must still be caught by the
    structural checks - that is the difference the note in the receipt claims."""
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        tampered = json.loads(json.dumps(receipt))
        tampered["variants"][0]["text"] = "Something else entirely"
        tampered["hashes"]["receipt_checksum_sha256"] = ttt._receipt_checksum(tampered)
        codes = [f["code"] for f in validate_experiment(tampered)["failures"]]
        assert "RECEIPT_CHECKSUM_MISMATCH" not in codes  # the checksum was recomputed
        assert "VARIANT_COPY_CHANGED" in codes


def test_single_row_default_never_wraps_or_drops_words() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        assert receipt["typography"]["max_lines"] == 1
        for variant in receipt["variants"]:
            assert variant["lines"] == [variant["text"]]
        assert len({v["font_px"] for v in receipt["variants"]}) == 1
        assert validate_experiment(receipt)["ok"]


def test_renderer_environment_change_requires_rebuild() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        receipt["renderer"]["pillow"] = "different-version"
        receipt["hashes"]["receipt_checksum_sha256"] = ttt._receipt_checksum(receipt)
        assert "RENDERER_ENV_CHANGED" in [f["code"] for f in validate_experiment(receipt)["failures"]]


def test_editable_layer_change_and_malformed_receipt_fail() -> None:
    with _workspace() as tmp:
        tmp = Path(tmp)
        receipt = _rebuild(tmp / "out", base=_make_base(tmp / "base.png"))
        path = Path(receipt["variants"][0]["layer_path"])
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
        assert "LAYER_HASH_MISMATCH" in [f["code"] for f in validate_experiment(receipt)["failures"]]
        assert not validate_experiment({"renderer": "broken"})["ok"]


def _run_all() -> int:
    tests = [
        (name, obj)
        for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - a runner, not a gate
            failed += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {name}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
