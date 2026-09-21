"""CLI for the deterministic text-only A/B/C thumbnail experiment.

    python tools/build_thumbnail_text_test.py \
        --base "D:/Boyd Clips/thumbwork/<CASE>/base_text_only.png" \
        --title "Judge Boyd audits the docket" \
        --a "She audited *the court* live" \
        --b "The court got *audited*" \
        --c "Another *audit* for the court" \
        --evidence-file work/<vid>/<vid>.transcript.json \
        --out "out/review/<CASE>/text_only"

`*stars*` mark the substring that renders in the house key-phrase yellow; the
markers are stripped before rendering, so the words are never edited. Pass
`--emphasis-a/b/c` instead when the substring should be named explicitly.

    python tools/build_thumbnail_text_test.py --validate out/review/<CASE>/text_only

re-opens the built experiment and reports every failed invariant.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips.thumbnail_text_test import (  # noqa: E402
    TextRectangle,
    TextVariant,
    ThumbnailTextTestError,
    Typography,
    build_text_only_experiment,
    validate_experiment,
)


def _split_emphasis(raw: str, explicit: str | None, label: str) -> TextVariant:
    """`*word*` marks the yellow run. Exactly one marked run is expected per
    headline; the markers never reach the renderer."""
    text = raw
    if explicit:
        if "*" in raw:
            raise SystemExit(f"--{label.lower()}: use either *markers* or --emphasis-{label.lower()}")
        return TextVariant(label, raw, explicit)
    marked = re.findall(r"\*([^*]+)\*", raw)
    if not marked:
        raise SystemExit(
            f"--{label.lower()}: no yellow emphasis - wrap the substring in *stars* "
            f"or pass --emphasis-{label.lower()}"
        )
    text = raw.replace("*", "")
    emphasis = " ".join(marked)
    if emphasis not in text:
        raise SystemExit(f"--{label.lower()}: the marked emphasis does not survive in the text")
    return TextVariant(label, text, emphasis)


def _parse_rect(raw: str | None) -> TextRectangle | None:
    if not raw:
        return None
    parts = [int(part) for part in re.split(r"[,\s]+", raw.strip()) if part]
    if len(parts) != 4:
        raise SystemExit("--rect wants x0,y0,x1,y1")
    return TextRectangle(*parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--validate", metavar="RECEIPT_OR_DIR",
                        help="re-check a built experiment instead of building one")
    parser.add_argument("--base", help="the ONE shared base image (background owned upstream)")
    parser.add_argument("--title", help="the one fixed video title for all three variants")
    parser.add_argument("--a", dest="text_a", help="variant A headline (mark yellow with *stars*)")
    parser.add_argument("--b", dest="text_b", help="variant B headline")
    parser.add_argument("--c", dest="text_c", help="variant C headline")
    parser.add_argument("--emphasis-a", help="explicit yellow substring for A")
    parser.add_argument("--emphasis-b", help="explicit yellow substring for B")
    parser.add_argument("--emphasis-c", help="explicit yellow substring for C")
    parser.add_argument("--evidence", help="source evidence text the headlines come from")
    parser.add_argument("--evidence-file", help="file to read the evidence text from")
    parser.add_argument("--out", help="output directory for the exports and the receipt")
    parser.add_argument("--rect", help="text rectangle x0,y0,x1,y1")
    parser.add_argument("--font", help="font file (default: the house Montserrat variable font)")
    parser.add_argument("--weight", type=int, default=700, help="variable-font weight (default 700)")
    parser.add_argument("--min-font-px", type=int, default=44)
    parser.add_argument("--max-font-px", type=int, default=120)
    parser.add_argument("--max-lines", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="print the receipt as JSON")
    args = parser.parse_args(argv)

    if args.validate:
        target = Path(args.validate)
        receipt = target / "thumbnail-text-only.json" if target.is_dir() else target
        report = validate_experiment(receipt)
        for failure in report["failures"]:
            print(f"FAIL {failure['code']}: {failure['detail']}")
        print("VALID" if report["ok"] else "INVALID", f"({target})")
        return 0 if report["ok"] else 3

    missing = [name for name, value in (("--base", args.base), ("--title", args.title),
                                        ("--a", args.text_a), ("--b", args.text_b),
                                        ("--c", args.text_c), ("--out", args.out))
               if not value]
    if missing:
        parser.error("build mode needs " + ", ".join(missing))
    evidence = args.evidence or ""
    if args.evidence_file:
        evidence = Path(args.evidence_file).read_text(encoding="utf-8")
    if not evidence.strip():
        parser.error("build mode needs --evidence or --evidence-file")

    typography = Typography(
        weight=args.weight,
        min_font_px=args.min_font_px,
        max_font_px=args.max_font_px,
        max_lines=args.max_lines,
    )
    if args.font:
        typography = dataclasses.replace(typography, font_path=Path(args.font))

    try:
        receipt = build_text_only_experiment(
            base=Path(args.base),
            title=args.title,
            variants=(
                _split_emphasis(args.text_a, args.emphasis_a, "A"),
                _split_emphasis(args.text_b, args.emphasis_b, "B"),
                _split_emphasis(args.text_c, args.emphasis_c, "C"),
            ),
            evidence=evidence,
            outdir=Path(args.out),
            rectangle=_parse_rect(args.rect),
            typography=typography,
        )
    except ThumbnailTextTestError as exc:
        for failure in exc.failures:
            print(f"REFUSED {failure.code}: {failure.detail}")
        print("nothing was written")
        return 2

    print(f"built {len(receipt['variants'])} variants, common font {receipt['typography']['font_px']}px")
    for record in receipt["variants"]:
        print(f"  {record['label']}: {record['png_path']}")
    print(f"receipt {Path(args.out) / 'thumbnail-text-only.json'}")
    report = validate_experiment(receipt)
    print("validate", "VALID" if report["ok"] else "INVALID")
    if args.json:
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
