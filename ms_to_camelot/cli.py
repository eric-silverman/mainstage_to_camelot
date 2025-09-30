import argparse
from pathlib import Path
from datetime import datetime
import json

from .parser_mainstage import parse_concert
from .emit_camelot import build_camelot_session
from .summary import render_summary


def main():
    parser = argparse.ArgumentParser(
        prog="ms-to-camelot",
        description="Convert a MainStage .concert into a Camelot-style session JSON (songs/scenes/splits)",
    )
    parser.add_argument("--input", "-i", required=True, help="Path to MainStage .concert bundle or ProjectData file")
    parser.add_argument("--output", "-o", default="out", help="Output directory (will be created if missing)")
    parser.add_argument("--flatten-sets", action="store_true", help="Map patches directly to songs (no scenes)")
    parser.add_argument("--dry-run", action="store_true", help="Print summary only; do not write files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logs")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"Input path not found: {in_path}")

    concert = parse_concert(in_path, verbose=args.verbose)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = concert.name or in_path.stem
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write extracted normalized JSON for debugging/transforms
    extracted = concert.to_dict()

    camelot = build_camelot_session(
        concert,
        flatten_sets=args.flatten_sets,
        source_path=str(in_path.resolve()),
    )

    summary_text = render_summary(concert, camelot)

    if args.dry_run:
        print(summary_text)
        return

    extracted_path = out_dir / f"{base_name}.extracted.json"
    camelot_path = out_dir / f"{base_name}.camelot.json"
    summary_path = out_dir / f"{base_name}.summary.txt"

    with extracted_path.open("w", encoding="utf-8") as f:
        json.dump(extracted, f, indent=2, ensure_ascii=False)
    with camelot_path.open("w", encoding="utf-8") as f:
        json.dump(camelot, f, indent=2, ensure_ascii=False)
    with summary_path.open("w", encoding="utf-8") as f:
        f.write(summary_text)

    if args.verbose:
        print(f"Wrote: {camelot_path}")
        print(f"Wrote: {extracted_path}")
        print(f"Wrote: {summary_path}")

