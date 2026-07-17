# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Two standalone Python scripts for turning PDFs into plain text/JSON via the `opendataloader_pdf` package. There is no package manifest, build system, or test suite in this directory — each script is run directly with `python`.

## Commands

Install the one dependency (not currently installed in this environment):

```
pip install opendataloader_pdf
```

Convert all PDFs in a directory to raw `opendataloader_pdf` JSON:

```
python batch_pdf_to_json.py <input_dir> <output_dir> [--recursive] [--quiet]
```

Post-process that raw JSON into per-page text and a flat `.txt`/`.processed.json`:

```
python postprocess_pdf_json.py <input_dir> <output_dir> [--recursive]
```

Typical pipeline: run `batch_pdf_to_json.py` on a folder of PDFs, then feed its `output_dir` as the `input_dir` for `postprocess_pdf_json.py`.

## Architecture

- `batch_pdf_to_json.py` — finds `*.pdf` files in a directory (optionally recursive), calls `opendataloader_pdf.convert(...)` once with the full file list, and writes one JSON file per PDF to `output_dir`.
- `postprocess_pdf_json.py` — reads each `opendataloader_pdf`-format JSON file and walks its nested `kids`/`list items` tree (`collect_text_by_page`) to pull out text `content` nodes keyed by `page number`. It normalizes whitespace per line, joins lines per page, then joins pages into one document. For each input file it writes two outputs: `<stem>.processed.json` (metadata + per-page text + full text) and `<stem>.txt` (full text only).

The `opendataloader_pdf` JSON tree shape (`kids`, `list items`, `content`, `page number`) is the load-bearing assumption in `postprocess_pdf_json.py::collect_text_by_page` — if the upstream library's output schema changes, that function is the one to update.
