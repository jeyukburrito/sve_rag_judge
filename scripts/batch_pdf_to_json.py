from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from opendataloader_pdf import convert


def iter_pdf_files(input_dir: Path, recursive: bool) -> Iterable[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    yield from sorted(path for path in input_dir.glob(pattern) if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert all PDF files in a directory to JSON with opendataloader_pdf."
    )
    parser.add_argument("input_dir", help="Directory containing PDF files")
    parser.add_argument("output_dir", help="Directory where JSON files will be written")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search subdirectories recursively",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress opendataloader_pdf console output",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist or is not a directory: {input_dir}")

    pdf_files = list(iter_pdf_files(input_dir, args.recursive))
    if not pdf_files:
        raise SystemExit(f"No PDF files found in: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Found {len(pdf_files)} PDF file(s).")
    for pdf_file in pdf_files:
        print(f"- {pdf_file}")

    convert(
        input_path=[str(path) for path in pdf_files],
        output_dir=str(output_dir),
        format="json",
        quiet=True if not args.quiet else True,
    )

    print(f"JSON output written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
