from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Iterable


def iter_json_files(input_dir: Path, recursive: bool) -> Iterable[Path]:
    pattern = "**/*.json" if recursive else "*.json"
    yield from sorted(path for path in input_dir.glob(pattern) if path.is_file())


def normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in value.split("\n")]
    return "\n".join(line for line in lines if line)


def collect_text_by_page(node: Any, pages: DefaultDict[int, list[str]]) -> None:
    if isinstance(node, dict):
        content = node.get("content")
        page_number = node.get("page number")
        if isinstance(content, str) and isinstance(page_number, int):
            text = normalize_text(content)
            if text:
                pages[page_number].append(text)

        list_items = node.get("list items")
        if isinstance(list_items, list):
            for item in list_items:
                collect_text_by_page(item, pages)

        kids = node.get("kids")
        if isinstance(kids, list):
            for item in kids:
                collect_text_by_page(item, pages)

    elif isinstance(node, list):
        for item in node:
            collect_text_by_page(item, pages)


def join_page_lines(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def process_file(input_path: Path, output_dir: Path) -> tuple[Path, Path]:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    pages: DefaultDict[int, list[str]] = defaultdict(list)
    collect_text_by_page(data.get("kids", []), pages)

    page_entries = []
    for page_number in sorted(pages):
        page_entries.append(
            {
                "page": page_number,
                "text": join_page_lines(pages[page_number]),
            }
        )

    full_text = "\n\n".join(
        page["text"] for page in page_entries if page["text"]
    ).strip()

    processed = {
        "file_name": data.get("file name"),
        "number_of_pages": data.get("number of pages"),
        "author": data.get("author"),
        "title": data.get("title"),
        "pages": page_entries,
        "text": full_text,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_output = output_dir / f"{input_path.stem}.processed.json"
    txt_output = output_dir / f"{input_path.stem}.txt"
    json_output.write_text(
        json.dumps(processed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    txt_output.write_text(full_text, encoding="utf-8")
    return json_output, txt_output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post-process opendataloader_pdf JSON into page-wise JSON and full text."
    )
    parser.add_argument("input_dir", help="Directory containing opendataloader_pdf JSON files")
    parser.add_argument("output_dir", help="Directory for processed outputs")
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search subdirectories recursively",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input directory does not exist or is not a directory: {input_dir}")

    json_files = list(iter_json_files(input_dir, args.recursive))
    if not json_files:
        raise SystemExit(f"No JSON files found in: {input_dir}")

    print(f"Found {len(json_files)} JSON file(s).")
    for json_file in json_files:
        processed_json, processed_txt = process_file(json_file, output_dir)
        print(f"- {json_file.name}")
        print(f"  -> {processed_json.name}")
        print(f"  -> {processed_txt.name}")

    print(f"Processed outputs written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
